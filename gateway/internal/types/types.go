// Package types holds the shared request/response shapes used across the gateway.
package types

// ToolCall is one tool invocation attached to an assistant message.
type ToolCall struct {
	ID       string         `json:"id,omitempty"`
	Type     string         `json:"type,omitempty"`
	Function ToolCallFn     `json:"function,omitempty"`
}

// ToolCallFn is the function body of a tool call.
type ToolCallFn struct {
	Name      string `json:"name,omitempty"`
	Arguments string `json:"arguments,omitempty"`
}

// ChatMessage is one message in an OpenAI-style conversation.
type ChatMessage struct {
	Role       string         `json:"role"`
	Content    any            `json:"content"` // string or []ContentBlock
	ToolCalls  []ToolCall     `json:"tool_calls,omitempty"`
	ToolCallID string         `json:"tool_call_id,omitempty"`
	Name       string         `json:"name,omitempty"`
}

// ContentBlock is one multimodal block inside ChatMessage.Content.
type ContentBlock struct {
	Type string `json:"type"`
	Text string `json:"text,omitempty"`
}

// ChatRequest is the unified inbound chat shape (OpenAI-compatible superset).
type ChatRequest struct {
	Model            string          `json:"model"`
	Messages         []ChatMessage   `json:"messages"`
	Temperature      *float64        `json:"temperature,omitempty"`
	TopP             *float64        `json:"top_p,omitempty"`
	MaxTokens        *int            `json:"max_tokens,omitempty"`
	Stop             []string        `json:"stop,omitempty"`
	Stream           bool            `json:"stream,omitempty"`
	FrequencyPenalty *float64        `json:"frequency_penalty,omitempty"`
	PresencePenalty  *float64        `json:"presence_penalty,omitempty"`
	N                *int            `json:"n,omitempty"`
	User             string          `json:"user,omitempty"`

	// Gateway extensions
	Provider  string `json:"provider,omitempty"`
	Project   string `json:"project,omitempty"`
	UseMemory bool   `json:"use_memory,omitempty"`
	UseCache  bool   `json:"use_cache,omitempty"`
}

// ChatResult is the normalized provider response.
type ChatResult struct {
	Content  string
	Model    string
	Provider string
	Usage    Usage
	Raw      any
}

// Usage tracks token consumption for a call.
type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

// StreamChunk is one delta on an SSE stream.
type StreamChunk struct {
	Content      string
	FinishReason string
	Model        string
}

// ExtractText flattens a ChatMessage.Content (string or block list) into text.
func ExtractText(content any) string {
	switch v := content.(type) {
	case nil:
		return ""
	case string:
		return v
	case []any:
		out := ""
		for _, item := range v {
			if blk, ok := item.(map[string]any); ok {
				if blk["type"] == "text" {
					if t, ok := blk["text"].(string); ok {
						out += t + " "
					}
				}
			} else if s, ok := item.(string); ok {
				out += s + " "
			}
		}
		return trim(out)
	default:
		return ""
	}
}

func trim(s string) string {
	for len(s) > 0 && (s[len(s)-1] == ' ' || s[len(s)-1] == '\n' || s[len(s)-1] == '\t') {
		s = s[:len(s)-1]
	}
	for len(s) > 0 && (s[0] == ' ' || s[0] == '\n' || s[0] == '\t') {
		s = s[1:]
	}
	return s
}
