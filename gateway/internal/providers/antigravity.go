// Antigravity / Google Cloud Code provider.
//
// Auth is Google PKCE OAuth; requests go to the Cloud Code Assist proxy with a
// Gemini-shaped request wrapped in the service envelope.
package providers

import (
	"bufio"
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/types"
)

// AntigravityProvider implements Google's Cloud Code agent endpoint.
type AntigravityProvider struct {
	baseURL      string
	defaultModel string
	cfg          ProviderConfig
	http         *http.Client
}

// NewAntigravity constructs the provider.
func NewAntigravity(cfg ProviderConfig) (Provider, error) {
	base := cfg.Overrides.ProviderBaseURL[TableAntigravity]
	if base == "" {
		base = "https://daily-cloudcode-pa.googleapis.com"
	}
	model := config_ModelFor(TableAntigravity, cfg)
	if model == "" {
		model = "gemini-3.1-pro-agent"
	}
	return &AntigravityProvider{
		baseURL:      strings.TrimRight(base, "/"),
		defaultModel: model,
		cfg:          cfg,
		http:         &http.Client{Timeout: 180 * time.Second},
	}, nil
}

func (a *AntigravityProvider) Name() string         { return TableAntigravity }
func (a *AntigravityProvider) DefaultModel() string { return a.defaultModel }

// Metadata describes Antigravity for /api/metrics.
func (a *AntigravityProvider) Metadata() Metadata {
	return Metadata{
		Name:         a.Name(),
		BaseURL:      a.baseURL,
		DefaultModel: a.defaultModel,
		Capabilities: map[string]bool{
			"chat": true, "streaming": true, "vision": true,
			"embeddings": false, "tool_calling": true, "reasoning": true,
		},
		MaxContext: 1_000_000,
	}
}

// openaiModelAlias maps "gemini-3.1-pro-high"-style names to physical ids.
var antigravityModelAlias = map[string]string{
	"gemini-3.1-pro-high":    "gemini-pro-agent",
	"gemini-3.1-pro-medium":  "gemini-pro-agent",
	"gemini-3.5-flash-high":  "gemini-3-flash-agent",
}

func antigravityPhysicalModel(model string) string {
	if v, ok := antigravityModelAlias[model]; ok {
		return v
	}
	return model
}

// Cloud Code envelope: OpenAI messages get translated into a Gemini-shaped
// `request` body and wrapped with project/agent metadata.
func (a *AntigravityProvider) buildEnvelope(req *types.ChatRequest, projectID string) ([]byte, error) {
	model := a.defaultModel
	if req.Model != "" {
		model = antigravityPhysicalModel(req.Model)
	}

	payload := map[string]any{
		"contents": messagesToGeminiContents(req.Messages),
	}
	if req.Temperature != nil || req.MaxTokens != nil || req.TopP != nil || len(req.Stop) > 0 {
		gc := map[string]any{}
		if req.Temperature != nil {
			gc["temperature"] = *req.Temperature
		}
		if req.MaxTokens != nil {
			gc["maxOutputTokens"] = *req.MaxTokens
		}
		if req.TopP != nil {
			gc["topP"] = *req.TopP
		}
		if len(req.Stop) > 0 {
			gc["stopSequences"] = req.Stop
		}
		payload["generationConfig"] = gc
	}

	wrapped := map[string]any{
		"project":           projectID,
		"model":             a.defaultModel,
		"requestType":       "agent",
		"requestId":         req.User, // approximates a stable per-request id
		"userAgent":         "antigravity",
		"request":           payload,
		"enabledCreditTypes": []string{"GOOGLE_ONE_AI"},
	}
	// The physical model id goes here, not the alias.
	wrapped["model"] = model

	return json.Marshal(wrapped)
}

// messagesToGeminiContents converts an OpenAI message list into the Gemini
// content envelope (user/model roles, tool messages folded as text, system
// hoisted to systemInstruction).
func messagesToGeminiContents(msgs []types.ChatMessage) []map[string]any {
	out := []map[string]any{}
	for _, m := range msgs {
		text := types.ExtractText(m.Content)
		switch m.Role {
		case "system":
			// Gemini carries system outside contents
			out = append([]map[string]any{{"role": "system", "parts": []any{map[string]any{"text": text}}}}, out...)
		case "user":
			out = append(out, map[string]any{
				"role":  "user",
				"parts": []any{map[string]any{"text": text}},
			})
		case "assistant":
			out = append(out, map[string]any{
				"role":  "model",
				"parts": []any{map[string]any{"text": text}},
			})
		case "tool":
			out = append(out, map[string]any{
				"role":  "user",
				"parts": []any{map[string]any{"text": "[tool result] " + text}},
			})
		}
	}
	return out
}

// Chat does a non-streaming Cloud Code call (server still streams via SSE —
// we consume the whole frame sequence).
func (a *AntigravityProvider) Chat(ctx Context, req *types.ChatRequest, apiKey string) (*types.ChatResult, error) {
	projectID, err := antigravityProjectID()
	if err != nil {
		return nil, err
	}
	body, err := a.buildEnvelope(req, projectID)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		a.baseURL+"/v1internal:streamGenerateContent?alt=sse", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	applyAntigravityHeaders(httpReq, apiKey)

	resp, err := a.http.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, &HTTPError{StatusCode: resp.StatusCode, Body: string(raw)}
	}

	content, usage := consumeGeminiSSE(resp.Body)
	model := a.defaultModel
	if req.Model != "" {
		model = antigravityPhysicalModel(req.Model)
	}

	return &types.ChatResult{
		Content:  content,
		Model:    model,
		Provider: a.Name(),
		Usage:    usage,
		Raw:      nil,
	}, nil
}

// ChatStream streams Cloud Code responses.
func (a *AntigravityProvider) ChatStream(ctx Context, req *types.ChatRequest, apiKey string) (<-chan types.StreamChunk, error) {
	projectID, err := antigravityProjectID()
	if err != nil {
		return nil, err
	}
	body, err := a.buildEnvelope(req, projectID)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		a.baseURL+"/v1internal:streamGenerateContent?alt=sse", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	applyAntigravityHeaders(httpReq, apiKey)

	resp, err := a.http.Do(httpReq)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		defer resp.Body.Close()
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, &HTTPError{StatusCode: resp.StatusCode, Body: string(raw)}
	}

	model := a.defaultModel
	if req.Model != "" {
		model = antigravityPhysicalModel(req.Model)
	}

	out := make(chan types.StreamChunk, 8)
	go func() {
		defer close(out)
		defer resp.Body.Close()
		reader := bufio.NewReaderSize(resp.Body, 64<<10)
		for {
			line, err := reader.ReadString('\n')
			if line == "" && err != nil {
				return
			}
			line = strings.TrimSpace(line)
			if !strings.HasPrefix(line, "data: ") {
				if err != nil {
					return
				}
				continue
			}
			payloadStr := strings.TrimPrefix(line, "data: ")
			if payloadStr == "[DONE]" {
				out <- types.StreamChunk{FinishReason: "stop", Model: model}
				return
			}
			text, done := geminiChunkText(payloadStr)
			if text != "" {
				out <- types.StreamChunk{Content: text, FinishReason: "", Model: model}
			}
			if done || err != nil {
				return
			}
		}
	}()
	return out, nil
}

// Health is true when an OAuth token exists for Antigravity.
func (a *AntigravityProvider) Health(ctx Context) (bool, error) {
	return a.cfg.APIKey != "" || cfgKeyFromOAuth("antigravity") != "", nil
}

// consumeGeminiSSE reads every "data: ..." frame and accumulates assistant text.
func consumeGeminiSSE(r io.Reader) (string, types.Usage) {
	var content strings.Builder
	usage := types.Usage{}
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		payload := strings.TrimPrefix(line, "data: ")
		if payload == "[DONE]" {
			break
		}
		text, done := geminiChunkText(payload)
		content.WriteString(text)
		if done {
			break
		}
	}
	return content.String(), usage
}

// geminiChunkText parses one SSE frame's payload JSON into plain text and
// returns it plus a "finish" marker when the chunk carries a finishReason.
func geminiChunkText(payload string) (string, bool) {
	var m map[string]any
	if json.Unmarshal([]byte(payload), &m) != nil {
		return "", false
	}
	// Cloud Code wraps Gemini in {"response": {...}}
	node := m
	if r, ok := m["response"].(map[string]any); ok {
		node = r
	}
	candidates, _ := node["candidates"].([]any)
	var text strings.Builder
	finish := false
	for _, c := range candidates {
		cand, _ := c.(map[string]any)
		content, _ := cand["content"].(map[string]any)
		parts, _ := content["parts"].([]any)
		for _, p := range parts {
			if pm, ok := p.(map[string]any); ok {
				if s, ok := pm["text"].(string); ok {
					text.WriteString(s)
				}
			}
		}
		if cand["finishReason"] == "STOP" {
			finish = true
		}
	}
	return text.String(), finish
}

func applyAntigravityHeaders(req *http.Request, apiKey string) {
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "antigravity/1.0")
}
