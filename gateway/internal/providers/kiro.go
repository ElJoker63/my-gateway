// Kiro AI provider — AWS CodeWhisperer Conversational Assistant API.
//
// Wire format: custom JSON envelope ("conversationState" + currentMessage).
// Responses come framed in AWS EventStream binary; we decode the frames and
// concatenate assistant text chunks.
package providers

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/types"
)

// KiroProvider is the AWS CodeWhisperer adapter (device-flow authenticated).
type KiroProvider struct {
	baseURL      string
	defaultModel string
	cfg          ProviderConfig
	http         *http.Client
}

// NewKiro builds a Kiro provider from shared configuration.
func NewKiro(cfg ProviderConfig) (Provider, error) {
	base := cfg.Overrides.ProviderBaseURL[TableKiro]
	if base == "" {
		// Default to US East; can be overridden via KIRO_BASE_URL
		base = "https://codewhisperer.us-east-1.amazonaws.com"
	}
	model := config_ModelFor(TableKiro, cfg)
	if model == "" {
		model = "claude-sonnet-4.5"
	}
	return &KiroProvider{
		baseURL:      strings.TrimRight(base, "/"),
		defaultModel: model,
		cfg:          cfg,
		http:         &http.Client{Timeout: 120 * time.Second},
	}, nil
}

func (k *KiroProvider) Name() string        { return TableKiro }
func (k *KiroProvider) DefaultModel() string { return k.defaultModel }

// Metadata describes Kiro for /api/metrics.
func (k *KiroProvider) Metadata() Metadata {
	return Metadata{
		Name:         k.Name(),
		BaseURL:      k.baseURL,
		DefaultModel: k.defaultModel,
		Capabilities: map[string]bool{
			"chat": true, "streaming": true, "vision": false,
			"embeddings": false, "tool_calling": false, "reasoning": true,
		},
		MaxContext: 200_000,
	}
}

// conversationState is the CodeWhisperer request envelope's payload shape.
type kiroRequest struct {
	ConversationState kiroConversationState `json:"conversationState"`
	ProfileArn        string                 `json:"profileArn,omitempty"`
	InferenceConfig   *kiroInferenceConfig   `json:"inferenceConfig,omitempty"`
}

type kiroConversationState struct {
	CurrentMessage kiroCurrentMessage  `json:"currentMessage"`
	History        []kiroHistoryItem   `json:"history,omitempty"`
	ChatTriggerType string             `json:"chatTriggerType"`
}

type kiroCurrentMessage struct {
	UserInputMessage kiroUserInputMessage `json:"userInputMessage"`
}

type kiroUserInputMessage struct {
	Content string `json:"content"`
	ModelID string `json:"modelId"`
	Origin  string `json:"origin"`
}

type kiroHistoryItem struct {
	UserInputMessage       kiroUserInputMessage          `json:"userInputMessage"`
	AssistantResponseMessage kiroAssistantResponseMessage `json:"assistantResponseMessage"`
}

type kiroAssistantResponseMessage struct {
	Content string `json:"content"`
}

type kiroInferenceConfig struct {
	MaxTokens   *int     `json:"maxTokens,omitempty"`
	Temperature *float64 `json:"temperature,omitempty"`
	TopP        *float64 `json:"topP,omitempty"`
	Stop        []string `json:"stop,omitempty"`
}

func buildKiroRequest(req *types.ChatRequest, model string, profileArn string) (*kiroRequest, error) {
	msgs := req.Messages
	lastUser := -1
	for i := len(msgs) - 1; i >= 0; i-- {
		if msgs[i].Role == "user" {
			lastUser = i
			break
		}
	}
	if lastUser < 0 {
		return nil, errors.New("kiro requires at least one user message")
	}

	current := kiroUserInputMessage{
		Content: types.ExtractText(msgs[lastUser].Content),
		ModelID: model,
		Origin:  "AI_EDITOR",
	}

	// Fold earlier turns into pairs for CodeWhisperer's history format.
	history := []kiroHistoryItem{}
	for i := 0; i+1 < lastUser; i += 2 {
		u := msgs[i]
		a := msgs[i+1]
		if u.Role == "user" && a.Role == "assistant" {
			history = append(history, kiroHistoryItem{
				UserInputMessage: kiroUserInputMessage{
					Content: types.ExtractText(u.Content),
					ModelID: model,
					Origin:  "AI_EDITOR",
				},
				AssistantResponseMessage: kiroAssistantResponseMessage{
					Content: types.ExtractText(a.Content),
				},
			})
		}
	}

	out := &kiroRequest{
		ConversationState: kiroConversationState{
			CurrentMessage:  kiroCurrentMessage{UserInputMessage: current},
			History:         history,
			ChatTriggerType: "MANUAL",
		},
	}
	if profileArn != "" {
		out.ProfileArn = profileArn
	}
	if req.MaxTokens != nil || req.Temperature != nil || req.TopP != nil || len(req.Stop) > 0 {
		out.InferenceConfig = &kiroInferenceConfig{
			MaxTokens:   req.MaxTokens,
			Temperature: req.Temperature,
			TopP:        req.TopP,
			Stop:        req.Stop,
		}
	}
	return out, nil
}

// Chat does a non-streaming CodeWhisperer call.
func (k *KiroProvider) Chat(ctx Context, req *types.ChatRequest, apiKey string) (*types.ChatResult, error) {
	model := k.defaultModel
	if req.Model != "" {
		model = req.Model
	}
	body, err := buildKiroRequest(req, model, "")
	if err != nil {
		return nil, err
	}
	buf, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		k.baseURL+"/generateAssistantResponse", bytes.NewReader(buf))
	if err != nil {
		return nil, err
	}
	applyKiroHeaders(httpReq, apiKey)

	resp, err := k.http.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, &HTTPError{StatusCode: resp.StatusCode, Body: string(raw)}
	}

	content := decodeKiroEventStream(resp.Body)
	return &types.ChatResult{
		Content:  content,
		Model:    model,
		Provider: k.Name(),
		Usage:    types.Usage{},
		Raw:      nil,
	}, nil
}

// ChatStream streams CodeWhisperer deltas (EventStream).
func (k *KiroProvider) ChatStream(ctx Context, req *types.ChatRequest, apiKey string) (<-chan types.StreamChunk, error) {
	model := k.defaultModel
	if req.Model != "" {
		model = req.Model
	}
	body, err := buildKiroRequest(req, model, "")
	if err != nil {
		return nil, err
	}
	buf, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		k.baseURL+"/generateAssistantResponse", bytes.NewReader(buf))
	if err != nil {
		return nil, err
	}
	applyKiroHeaders(httpReq, apiKey)

	resp, err := k.http.Do(httpReq)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		defer resp.Body.Close()
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, &HTTPError{StatusCode: resp.StatusCode, Body: string(raw)}
	}

	out := make(chan types.StreamChunk, 8)
	go func() {
		defer close(out)
		text := decodeKiroEventStream(resp.Body)
		for _, chunk := range chunkString(text, 256) {
			select {
			case out <- types.StreamChunk{Content: chunk, Model: model}:
			case <-ctx.Done():
				return
			}
		}
		out <- types.StreamChunk{FinishReason: "stop", Model: model}
	}()
	return out, nil
}

// Health is local-only: Kiro is only available if we hold an OAuth token.
func (k *KiroProvider) Health(ctx Context) (bool, error) {
	return k.cfg.APIKey != "" || cfgKeyFromOAuth("kiro") != "", nil
}

func applyKiroHeaders(req *http.Request, apiKey string) {
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-amz-target", "AmazonCodeWhispererStreamingService.GenerateAssistantResponse")
	req.Header.Set("x-amz-user-agent", "aws-sdk-js/3.0.0 kiro/0.1")
}

// decodeKiroEventStream reads AWS EventStream frames off the body and
// concatenates every {"content": ...} JSON payload it finds.
func decodeKiroEventStream(r io.Reader) string {
	buf, err := io.ReadAll(r)
	if err != nil {
		return ""
	}

	var parts []string
	for off := 0; off+16 <= len(buf); {
		totalLen := int(decodeUint32(buf[off : off+4]))
		if totalLen < 16 || off+totalLen > len(buf) {
			break
		}
		headersLen := int(decodeUint32(buf[off+4 : off+8]))
		payload := buf[off+12+headersLen : off+totalLen-4]
		var m map[string]any
		if json.Unmarshal(payload, &m) == nil {
			for _, key := range []string{"content", "text"} {
				if v, ok := m[key].(string); ok && v != "" {
					parts = append(parts, v)
					break
				}
			}
		}
		off += totalLen
	}
	return strings.Join(parts, "")
}

func decodeUint32(b []byte) uint32 {
	return uint32(b[0])<<24 | uint32(b[1])<<16 | uint32(b[2])<<8 | uint32(b[3])
}

// chunkString splits a string into approximately-n-sized chunks (used when the
// upstream EventStream sends one giant concatenated answer).
func chunkString(s string, n int) []string {
	if n <= 0 || len(s) <= n {
		return []string{s}
	}
	out := make([]string, 0, len(s)/n+1)
	for i := 0; i < len(s); i += n {
		end := i + n
		if end > len(s) {
			end = len(s)
		}
		out = append(out, s[i:end])
	}
	return out
}

func config_ModelFor(provider string, cfg ProviderConfig) string {
	if m := cfg.Overrides.ProviderModels[provider]; m != "" {
		return m
	}
	return ""
}
