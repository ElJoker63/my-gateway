package api

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/combos"
	"github.com/ElJoker63/my-gateway/gateway/internal/keymanager"
	"github.com/ElJoker63/my-gateway/gateway/internal/providers"
	"github.com/ElJoker63/my-gateway/gateway/internal/racing"
	"github.com/ElJoker63/my-gateway/gateway/internal/types"
)

// handleChat serves POST /v1/chat/completions (OpenAI-compatible).
func (s *Server) handleChat(w http.ResponseWriter, r *http.Request) {
	var req types.ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid request body: "+err.Error())
		return
	}
	if len(req.Messages) == 0 {
		s.writeError(w, http.StatusBadRequest, "messages is required")
		return
	}
	if req.Project == "" {
		req.Project = "default"
	}
	s.dispatchChat(w, r, &req, "openai")
}

// handleAnthropicChat serves POST /v1/messages (Anthropic shape).
func (s *Server) handleAnthropicChat(w http.ResponseWriter, r *http.Request) {
	var req types.ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	s.dispatchChat(w, r, &req, "anthropic")
}

// handleGatewayChat serves POST /api/chat (our simplified shape).
func (s *Server) handleGatewayChat(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Project   string `json:"project"`
		Message   string `json:"message"`
		Provider  string `json:"provider"`
		Model     string `json:"model"`
		UseMemory bool   `json:"use_memory"`
		UseCache  bool   `json:"use_cache"`
		Stream    bool   `json:"stream"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if strings.TrimSpace(body.Message) == "" {
		s.writeError(w, http.StatusBadRequest, "message is required")
		return
	}
	project := body.Project
	if project == "" {
		project = "default"
	}
	req := &types.ChatRequest{
		Model:     body.Model,
		Messages:  []types.ChatMessage{{Role: "user", Content: body.Message}},
		Stream:    body.Stream,
		Provider:  body.Provider,
		Project:   project,
		UseCache:  body.UseCache,
		UseMemory: body.UseMemory,
	}
	s.dispatchChat(w, r, req, "gateway")
}

// dispatchChat picks the direct or combo route.
func (s *Server) dispatchChat(w http.ResponseWriter, r *http.Request, req *types.ChatRequest, format string) {
	started := time.Now()

	providerName := req.Provider
	if providerName == "" {
		providerName = s.cfg.DefaultProvider
	}

	if combo, ok := s.comboFor(req.Model); ok {
		s.runCombo(w, r, req, combo, format, started, providerName)
		return
	}

	provider, ok := s.providers[providerName]
	if !ok {
		s.writeError(w, http.StatusBadRequest, "unknown provider: "+providerName)
		return
	}
	s.runDirect(w, r, req, provider, providerName, format, started)
}

// runDirect handles the non-combo path: cache → memory → key → call → record.
func (s *Server) runDirect(w http.ResponseWriter, r *http.Request, req *types.ChatRequest, provider providers.Provider, providerName, format string, started time.Time) {
	ctx := r.Context()
	params := chatParams(req)

	model := provider.DefaultModel()
	if req.Model != "" && !strings.HasPrefix(req.Model, "combo:") {
		model = req.Model
	}

	if req.UseCache && !req.Stream && s.cache != nil {
		key := cacheLookupKey(req.Messages, model, req.Project, params)
		if hit, ok := s.cache.Get(ctx, key); ok {
			writeChatResponse(w, format, hit, true)
			return
		}
	}

	messages := req.Messages
	if req.UseMemory && s.memoryMgr != nil && req.Project != "" && req.Project != "default" {
		if enriched, err := s.memoryMgr.EnrichContext(ctx, req.Project, messages); err == nil && len(enriched) > 0 {
			messages = enriched
		}
	}

	key, err := s.resolveAuth(ctx, providerName)
	if err != nil {
		s.writeUpstreamError(w, providerName, err)
		return
	}
	callReq := *req
	callReq.Messages = messages
	callReq.Model = model

	if req.Stream {
		s.streamChat(w, r, provider, &callReq, key, format, started, providerName)
		return
	}

	result, err := chatWithRetry(ctx, provider, &callReq, key, 2)
	if err != nil {
		if s.breaker != nil {
			s.breaker.Failure(providerName, model)
		}
		s.writeUpstreamError(w, providerName, err)
		return
	}
	if s.breaker != nil {
		s.breaker.Success(providerName, model)
	}
	if s.metrics != nil {
		s.metrics.Record(providerName, result.Model, msSince(started), true, result.Usage.TotalTokens, false, false)
	}

	if req.UseCache && s.cache != nil {
		payload := map[string]any{
			"content": result.Content,
			"model":   result.Model,
			"usage":   result.Usage,
		}
		s.cache.Set(ctx, cacheLookupKey(req.Messages, model, req.Project, params), payload, req.Project)
	}

	if req.UseMemory && s.memoryMgr != nil && req.Project != "" && req.Project != "default" {
		messages := req.Messages
		content := result.Content
		project := req.Project
		go func() {
			ctx2, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = s.memoryMgr.StoreConversation(ctx2, project, messages, content)
		}()
	}

	writeChatResponse(w, format, map[string]any{
		"content": result.Content,
		"model":   result.Model,
		"usage":   result.Usage,
	}, false)
}

// runCombo drives the combo's strategy to completion.
func (s *Server) runCombo(w http.ResponseWriter, r *http.Request, req *types.ChatRequest, combo *combos.Combo, format string, started time.Time, defaultProvider string) {
	ctx := r.Context()

	outcome, err := racing.Execute(ctx, combo, s.keys, func(cctx context.Context, target combos.Target) (any, error) {
		provider := s.providers[target.Provider]
		if provider == nil {
			return nil, fmt.Errorf("provider %q not configured", target.Provider)
		}
		key, err := s.resolveAuth(cctx, target.Provider)
		if err != nil {
			return nil, err
		}
		callReq := *req
		callReq.Model = target.Model
		if callReq.Model == "" {
			callReq.Model = provider.DefaultModel()
		}
		if req.Stream {
			chunks, err := provider.ChatStream(cctx, &callReq, key)
			if err != nil {
				return nil, err
			}
			var buf strings.Builder
			for ch := range chunks {
				buf.WriteString(ch.Content)
			}
			return &types.ChatResult{Content: buf.String(), Model: callReq.Model, Provider: target.Provider}, nil
		}
		return provider.Chat(cctx, &callReq, key)
	}, racing.Options{})

	if err != nil {
		s.writeUpstreamError(w, "combo:"+combo.Name, err)
		return
	}
	res, _ := outcome.Response.(*types.ChatResult)
	if res == nil {
		s.writeError(w, http.StatusInternalServerError, "unexpected combo result type")
		return
	}
	if s.metrics != nil {
		s.metrics.Record(outcome.Target.Provider, res.Model, msSince(started), true, res.Usage.TotalTokens,
			combo.Strategy == combos.StrategyRace, combo.Strategy == combos.StrategyRace)
	}
	writeChatResponse(w, format, map[string]any{
		"content":  res.Content,
		"model":    res.Model,
		"usage":    res.Usage,
		"provider": res.Provider,
	}, false)
}

// streamChat pipes provider chunks as SSE.
func (s *Server) streamChat(w http.ResponseWriter, r *http.Request, provider providers.Provider, req *types.ChatRequest, key, format string, started time.Time, providerName string) {
	chunks, err := provider.ChatStream(r.Context(), req, key)
	if err != nil {
		s.writeUpstreamError(w, providerName, err)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)
	flusher, _ := w.(http.Flusher)

	model := req.Model
	var full strings.Builder

	for ch := range chunks {
		if ch.Content != "" {
			full.WriteString(ch.Content)
		}
		fmt.Fprintf(w, "data: %s\n\n", sseFrame(format, model, ch))
		if flusher != nil {
			flusher.Flush()
		}
	}
	fmt.Fprint(w, "data: [DONE]\n\n")
	if flusher != nil {
		flusher.Flush()
	}

	if s.metrics != nil {
		s.metrics.Record(providerName, model, msSince(started), true, 0, false, false)
	}
	if s.memoryMgr != nil && req.Project != "" && req.Project != "default" {
		messages := req.Messages
		content := full.String()
		project := req.Project
		go func() {
			ctx2, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = s.memoryMgr.StoreConversation(ctx2, project, messages, content)
		}()
	}
	if s.breaker != nil {
		s.breaker.Success(providerName, model)
	}
}

// resolveAuth picks the key from OAuth store or the KeyManager pool.
func (s *Server) resolveAuth(ctx context.Context, providerName string) (string, error) {
	if providerName == providers.TableKiro || providerName == providers.TableAntigravity {
		if s.oauthMgr != nil {
			if tok := s.oauthMgr.AccessToken(providerName); tok != "" {
				return tok, nil
			}
		}
		return "", fmt.Errorf("%s is not connected — finish OAuth via /api/oauth/%s/start first", providerName, providerName)
	}
	if s.keys == nil {
		return "", errors.New("key manager not ready")
	}
	ki, err := s.keys.Acquire(ctx, providerName)
	if err != nil {
		return "", err
	}
	return ki.Key, nil
}

// chatWithRetry retries transient failures (5xx/429).
func chatWithRetry(ctx context.Context, provider providers.Provider, req *types.ChatRequest, key string, maxTries int) (*types.ChatResult, error) {
	var lastErr error
	for i := 0; i < maxTries; i++ {
		res, err := provider.Chat(ctx, req, key)
		if err == nil {
			return res, nil
		}
		lastErr = err
		var he *providers.HTTPError
		if errors.As(err, &he) && he.StatusCode < 500 && he.StatusCode != 429 {
			break
		}
	}
	return nil, lastErr
}

// comboFor resolves a model string to a combo, or nil.
func (s *Server) comboFor(model string) (*combos.Combo, bool) {
	if s.combos == nil || model == "" {
		return nil, false
	}
	return s.combos.Get(context.Background(), model)
}

// ---------- shape + helpers ----------

func chatParams(req *types.ChatRequest) map[string]any {
	out := map[string]any{}
	if req.Temperature != nil {
		out["temperature"] = *req.Temperature
	}
	if req.TopP != nil {
		out["top_p"] = *req.TopP
	}
	if req.MaxTokens != nil {
		out["max_tokens"] = *req.MaxTokens
	}
	if req.N != nil {
		out["n"] = *req.N
	}
	if len(req.Stop) > 0 {
		out["stop"] = req.Stop
	}
	return out
}

func cacheLookupKey(messages []types.ChatMessage, model, project string, params map[string]any) string {
	blob := map[string]any{
		"messages": messages,
		"model":    model,
		"project":  project,
		"params":   params,
	}
	buf, _ := json.Marshal(blob)
	sum := sha256.Sum256(buf)
	return hex.EncodeToString(sum[:])
}

func msSince(t time.Time) float64 { return float64(time.Since(t).Milliseconds()) }

func sseFrame(format, model string, ch types.StreamChunk) string {
	var frame map[string]any
	if format == "anthropic" {
		frame = map[string]any{
			"type":  "content_block_delta",
			"index": 0,
			"delta": map[string]any{"type": "text_delta", "text": ch.Content},
		}
	} else {
		frame = map[string]any{
			"id":      fmt.Sprintf("chatcmpl-%d", time.Now().UnixMilli()),
			"object":  "chat.completion.chunk",
			"created": time.Now().Unix(),
			"model":   model,
			"choices": []any{map[string]any{
				"index":         0,
				"delta":         map[string]any{"content": ch.Content},
				"finish_reason": ch.FinishReason,
			}},
		}
	}
	buf, _ := json.Marshal(frame)
	return string(buf)
}

func writeChatResponse(w http.ResponseWriter, format string, payload map[string]any, cached bool) {
	w.Header().Set("Content-Type", "application/json")
	out := map[string]any{
		"response": payload["content"],
		"model":    payload["model"],
		"usage":    payload["usage"],
		"cached":   cached,
	}
	if format == "anthropic" {
		out["type"] = "message"
		out["role"] = "assistant"
		out["content"] = []any{map[string]any{"type": "text", "text": payload["content"]}}
		delete(out, "response")
	}
	_ = json.NewEncoder(w).Encode(out)
}

func (s *Server) writeUpstreamError(w http.ResponseWriter, providerName string, err error) {
	var he *providers.HTTPError
	if errors.As(err, &he) && he.StatusCode == 429 {
		s.writeError(w, http.StatusTooManyRequests, "provider rate limited")
		return
	}
	if errors.Is(err, keymanager.ErrAllLimited) || errors.Is(err, keymanager.ErrNoKeys) {
		s.writeError(w, http.StatusServiceUnavailable, "no API keys available for provider "+providerName)
		return
	}
	slog.Warn("upstream call failed", "provider", providerName, "err", err)
	s.writeError(w, http.StatusBadGateway, "provider "+providerName+" failed")
}
