// Package providers holds every upstream adapter: OpenAI-compatible ones share
// in openai.go, and Kiro / Antigravity have their own wire formats.
//
// Each provider has:
//   - name: stable slug ("nvidia")
//   - base URL, default model, capabilities
//   - optional custom request envelope/headers
//   - optional embedding model
package providers

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/config"
	"github.com/ElJoker63/my-gateway/gateway/internal/types"
)

// Provider is what the chat pipeline calls.
type Provider interface {
	Name() string
	Chat(ctx Context, req *types.ChatRequest, apiKey string) (*types.ChatResult, error)
	ChatStream(ctx Context, req *types.ChatRequest, apiKey string) (<-chan types.StreamChunk, error)
	Health(ctx Context) (bool, error)
	Metadata() Metadata
	DefaultModel() string
}

// Context is the per-request context (just the std context, aliased in case
// we want to enrich later).
type Context = context.Context

// Metadata reports what this provider can do.
type Metadata struct {
	Name         string                 `json:"name"`
	BaseURL      string                 `json:"base_url"`
	DefaultModel string                 `json:"default_model"`
	Capabilities map[string]bool        `json:"capabilities"`
	MaxContext   int                    `json:"max_context"`
	Extra        map[string]any         `json:"extra,omitempty"`
}

// Registry maps provider name → constructor.
type Registry struct {
	byName map[string]func(cfg ProviderConfig) (Provider, error)
}

// NewRegistry returns an empty registry.
func NewRegistry() *Registry {
	return &Registry{byName: map[string]func(ProviderConfig) (Provider, error){}}
}

// Register stores a provider constructor.
func (r *Registry) Register(name string, build func(cfg ProviderConfig) (Provider, error)) {
	r.byName[name] = build
}

// NewProvider instantiates a provider by name.
func (r *Registry) NewProvider(name string, cfg ProviderConfig) (Provider, error) {
	build, ok := r.byName[name]
	if !ok {
		return nil, fmt.Errorf("unknown provider %q", name)
	}
	return build(cfg)
}

// Names returns every registered name.
func (r *Registry) Names() []string {
	out := make([]string, 0, len(r.byName))
	for n := range r.byName {
		out = append(out, n)
	}
	return out
}

// RegistryDefault is the registry with every provider built-in.
var RegistryDefault = NewRegistry()

func init() {
	RegisterDefaults(RegistryDefault)
}

// RegisterDefaults wires every built-in provider.
func RegisterDefaults(r *Registry) {
	for name, cfg := range providerSpecs() {
		n := name
		c := cfg
		r.Register(n, func(pcfg ProviderConfig) (Provider, error) {
			return newOpenAICompatible(n, c, pcfg)
		})
	}
	r.Register(TableKiro, func(cfg ProviderConfig) (Provider, error) { return NewKiro(cfg) })
	r.Register(TableAntigravity, func(cfg ProviderConfig) (Provider, error) { return NewAntigravity(cfg) })
}

// Table provider names (needed to avoid import cycles between config and registry).
const (
	TableKiro        = "kiro"
	TableAntigravity = "antigravity"
)

// ProviderSpec is the static description for one OpenAI-compatible provider.
type ProviderSpec struct {
	Name              string
	BaseURL           string
	DefaultModel      string
	EmbeddingModel    string
	Capabilities      map[string]bool
	MaxContext        int
	RequestWrapper    func(body map[string]any) map[string]any // optional pre-send transform
	ExtraHeaders      map[string]string                        // static extra headers
	DefaultModelAlias map[string]string                        // alias → physical id
	ModelsURLOverride string                                   // if /models differs from base
}

// providerSpecs returns every OpenAI-compatible spec.
func providerSpecs() map[string]ProviderSpec {
	out := map[string]ProviderSpec{}
	for _, s := range providerCatalog {
		out[s.Name] = s
	}
	return out
}

// ProviderConfig is the per-instance settings bundle.
type ProviderConfig struct {
	APIKey          string
	AllowedRoots    []string
	Logger          *slog.Logger
	Overrides       config.Settings // resolved env for {PROVIDER}_BASE_URL etc
	EmbeddingModel  string          // from Settings embedding override
}

// ------------------------------
// OpenAI-compatible adapter
// ------------------------------

type openAICompatible struct {
	name        string
	baseURL     string
	defaultModel string
	spec        ProviderSpec
	cfg         ProviderConfig
	http        *http.Client
}

func newOpenAICompatible(name string, spec ProviderSpec, cfg ProviderConfig) (Provider, error) {
	base := cfg.Overrides.ProviderBaseURL[name]
	if base == "" {
		base = spec.BaseURL
	}
	if base == "" {
		return nil, fmt.Errorf("provider %q has no base URL configured", name)
	}
	model := cfg.EmbeddingModel
	if model == "" {
		model = spec.DefaultModel
	}
	return &openAICompatible{
		name:         name,
		baseURL:      strings.TrimRight(base, "/"),
		defaultModel: model,
		spec:         spec,
		cfg:          cfg,
		http: &http.Client{
			Timeout: 120 * time.Second,
		},
	}, nil
}

func (o *openAICompatible) Name() string { return o.name }
func (o *openAICompatible) DefaultModel() string { return o.defaultModel }

func (o *openAICompatible) Metadata() Metadata {
	return Metadata{
		Name:         o.name,
		BaseURL:      o.baseURL,
		DefaultModel: o.defaultModel,
		Capabilities: o.spec.Capabilities,
		MaxContext:   o.spec.MaxContext,
	}
}

func (o *openAICompatible) authHeaders(apiKey string) map[string]string {
	h := map[string]string{
		"Authorization": "Bearer " + apiKey,
		"Content-Type":  "application/json",
	}
	for k, v := range o.spec.ExtraHeaders {
		h[k] = v
	}
	return h
}

// mapModel resolves model aliases ("gemini-3.1-pro-high" → "gemini-pro-agent").
func (o *openAICompatible) mapModel(model string) string {
	if m, ok := o.spec.DefaultModelAlias[model]; ok {
		return m
	}
	return model
}

// buildRequestBody converts ChatRequest to the OpenAI wire form and applies
// the provider's request wrapper (e.g., Cloudflare's account-scoped URL).
func (o *openAICompatible) buildRequestBody(req *types.ChatRequest, model string, stream bool) ([]byte, error) {
	messages := make([]map[string]any, 0, len(req.Messages))
	for _, m := range req.Messages {
		messages = append(messages, map[string]any{
			"role":         m.Role,
			"content":      m.Content,
			"tool_calls":   m.ToolCalls,
			"tool_call_id": m.ToolCallID,
			"name":         m.Name,
		})
	}

	body := map[string]any{
		"model":    o.mapModel(model),
		"messages": messages,
	}
	if req.Temperature != nil {
		body["temperature"] = *req.Temperature
	}
	if req.TopP != nil {
		body["top_p"] = *req.TopP
	}
	if req.MaxTokens != nil {
		body["max_tokens"] = *req.MaxTokens
	}
	if len(req.Stop) > 0 {
		body["stop"] = req.Stop
	}
	if req.N != nil {
		body["n"] = *req.N
	}
	if req.FrequencyPenalty != nil {
		body["frequency_penalty"] = *req.FrequencyPenalty
	}
	if req.PresencePenalty != nil {
		body["presence_penalty"] = *req.PresencePenalty
	}
	if req.User != "" {
		body["user"] = req.User
	}
	if stream {
		body["stream"] = true
	}
	if o.spec.RequestWrapper != nil {
		body = o.spec.RequestWrapper(body)
	}
	return json.Marshal(body)
}

// Chat does a non-streaming call.
func (o *openAICompatible) Chat(ctx Context, req *types.ChatRequest, apiKey string) (*types.ChatResult, error) {
	model := o.defaultModel
	if req.Model != "" {
		model = o.mapModel(req.Model)
	}
	body, err := o.buildRequestBody(req, model, false)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		o.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	for k, v := range o.authHeaders(apiKey) {
		httpReq.Header.Set(k, v)
	}

	resp, err := o.http.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		buf, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, &HTTPError{StatusCode: resp.StatusCode, Body: string(buf)}
	}

	var payload map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}
	return o.parseChatResponse(payload, model)
}

// parseChatResponse plucks content + usage out of an OpenAI reply.
func (o *openAICompatible) parseChatResponse(payload map[string]any, model string) (*types.ChatResult, error) {
	choices, _ := payload["choices"].([]any)
	if len(choices) == 0 {
		return nil, errors.New("no choices in upstream response")
	}
	choice, _ := choices[0].(map[string]any)
	message, _ := choice["message"].(map[string]any)

	content := ""
	switch v := message["content"].(type) {
	case string:
		content = v
	case []any:
		for _, part := range v {
			if blk, ok := part.(map[string]any); ok && blk["type"] == "text" {
				if s, ok := blk["text"].(string); ok {
					content += s
				}
			}
		}
	}

	usage := types.Usage{}
	if u, ok := payload["usage"].(map[string]any); ok {
		usage.PromptTokens = intOf(u, "prompt_tokens")
		usage.CompletionTokens = intOf(u, "completion_tokens")
		usage.TotalTokens = intOf(u, "total_tokens")
	}

	return &types.ChatResult{
		Content:  content,
		Model:    strOf(payload, "model", model),
		Provider: o.name,
		Usage:    usage,
		Raw:      payload,
	}, nil
}

// ChatStream streams SSE chunks.
func (o *openAICompatible) ChatStream(ctx Context, req *types.ChatRequest, apiKey string) (<-chan types.StreamChunk, error) {
	model := o.defaultModel
	if req.Model != "" {
		model = o.mapModel(req.Model)
	}
	body, err := o.buildRequestBody(req, model, true)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		o.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	for k, v := range o.authHeaders(apiKey) {
		httpReq.Header.Set(k, v)
	}
	httpReq.Header.Set("Accept", "text/event-stream")

	resp, err := o.http.Do(httpReq)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode >= 400 {
		defer resp.Body.Close()
		buf, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, &HTTPError{StatusCode: resp.StatusCode, Body: string(buf)}
	}

	out := make(chan types.StreamChunk, 8)
	go o.streamLoop(ctx, resp, model, out)
	return out, nil
}

// streamLoop reads SSE lines and fans them out to the channel until [DONE].
func (o *openAICompatible) streamLoop(ctx Context, resp *http.Response, model string, out chan<- types.StreamChunk) {
	defer close(out)
	defer resp.Body.Close()

	reader := bufio.NewReaderSize(resp.Body, 64<<10)
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		line, err := reader.ReadString('\n')
		if err != nil && err != io.EOF {
			return
		}
		line = strings.TrimSpace(line)
		if line == "" {
			if err == io.EOF {
				return
			}
			continue
		}
		if !strings.HasPrefix(line, "data: ") {
			if err == io.EOF {
				return
			}
			continue
		}
		data := strings.TrimPrefix(line, "data: ")
		if data == "[DONE]" {
			out <- types.StreamChunk{Content: "", FinishReason: "stop", Model: model}
			return
		}
		var chunk map[string]any
		if err := json.Unmarshal([]byte(data), &chunk); err != nil {
			if err == io.EOF {
				return
			}
			continue
		}
		choices, _ := chunk["choices"].([]any)
		if len(choices) == 0 {
			if err == io.EOF {
				return
			}
			continue
		}
		choice, _ := choices[0].(map[string]any)
		delta, _ := choice["delta"].(map[string]any)
		finish, _ := choice["finish_reason"].(string)
		content, _ := delta["content"].(string)

		if reasoning, ok := delta["reasoning_content"].(string); ok && reasoning != "" {
			content = reasoning + content
		}
		out <- types.StreamChunk{Content: content, FinishReason: finish, Model: model}
		if err == io.EOF {
			return
		}
	}
}

// Health pings /models with the provider's key (401/5xx → false).
func (o *openAICompatible) Health(ctx Context) (bool, error) {
	var url string
	if o.spec.ModelsURLOverride != "" {
		url = o.spec.ModelsURLOverride
	} else {
		url = o.baseURL + "/models"
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return false, err
	}
	key := o.cfg.APIKey
	if k := o.providerKeyFromEnv(); k != "" {
		key = k
	}
	if key != "" {
		req.Header.Set("Authorization", "Bearer "+key)
	}

	client := o.http
	// dedicated short timeout for health checks
	client = &http.Client{Timeout: 8 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return false, nil
	}
	defer resp.Body.Close()
	return resp.StatusCode < 400, nil
}

// providerKeyFromEnv reads {NAME}_API_KEY env (upper-case) for cases where the
// ProviderConfig wasn't pre-populated.
func (o *openAICompatible) providerKeyFromEnv() string {
	return getenv(strings.ToUpper(o.name) + "_API_KEY")
}

func getenv(k string) string {
	return os.Getenv(k)
}

// ----------------- helpers -----------------

// HTTPError wraps a non-2xx upstream response.
type HTTPError struct {
	StatusCode int
	Body       string
}

func (e *HTTPError) Error() string {
	return fmt.Sprintf("upstream HTTP %d: %s", e.StatusCode, firstN(e.Body, 300))
}

func firstN(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

func strOf(m map[string]any, key, fallback string) string {
	if v, ok := m[key].(string); ok && v != "" {
		return v
	}
	return fallback
}

func intOf(m map[string]any, key string) int {
	switch v := m[key].(type) {
	case float64:
		return int(v)
	case int:
		return v
	default:
		return 0
	}
}
