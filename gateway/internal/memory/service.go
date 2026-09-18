package memory

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/types"
)

// EnrichContext prepends relevant project memories to a conversation.
// The system prompt (if any) becomes the memory-carrier; a fresh leading
// system message is added when the conversation lacks one.
func (s *Service) EnrichContext(ctx context.Context, project string, messages []types.ChatMessage) ([]types.ChatMessage, error) {
	if project == "" || project == "default" {
		return messages, nil
	}

	// Extract last user message; the memory search uses it as the query.
	var query string
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Role == "user" {
			query = types.ExtractText(messages[i].Content)
			break
		}
	}
	if query == "" {
		return messages, nil
	}

	collection := CollectionName(project)
	if !s.collectionExists(ctx, collection) {
		return messages, nil
	}

	// Embed the query using whatever the local service would use
	// (this gateway only supports fetch-style remote embeddings for now).
	emb := s.embedText(ctx, query)
	if len(emb) == 0 {
		return messages, nil
	}

	results, err := s.Search(ctx, collection, emb, 5, 0.5)
	if err != nil || len(results) == 0 {
		return messages, nil
	}

	var parts []string
	parts = append(parts,
		fmt.Sprintf("[Gateway Context — Project: %s]", project),
		"The following is relevant context retrieved from the project's memory.",
		"Use it to inform your response, but only if relevant to the user's question.",
		"",
	)
	for _, r := range results {
		text, _ := r.Payload["text"].(string)
		typ, _ := r.Payload["type"].(string)
		if text == "" {
			continue
		}
		parts = append(parts, fmt.Sprintf("--- [%s] [relevance: %.2f]\n%s", strings.ToUpper(typ), r.Score, text))
	}
	ctxBlock := strings.Join(parts, "\n\n")

	out := make([]types.ChatMessage, 0, len(messages)+1)
	if len(messages) > 0 && messages[0].Role == "system" {
		head := messages[0]
		text := types.ExtractText(head.Content)
		head.Content = text + "\n\n" + ctxBlock
		out = append(out, head)
	} else {
		out = append(out, types.ChatMessage{Role: "system", Content: ctxBlock})
	}
	out = append(out, messages...)
	return out, nil
}

// StoreConversation saves a (user, assistant) exchange for later recall.
func (s *Service) StoreConversation(ctx context.Context, project string, messages []types.ChatMessage, response string) error {
	if project == "" || project == "default" || response == "" {
		return nil
	}
	var lastUser string
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Role == "user" {
			lastUser = types.ExtractText(messages[i].Content)
			break
		}
	}
	if len(lastUser) < 10 || len(response) < 10 {
		return nil
	}

	content := fmt.Sprintf("Q: %s\nA: %s", truncate(lastUser, 400), truncate(response, 800))
	emb := s.embedText(ctx, content)
	if len(emb) == 0 {
		return nil
	}
	point := Point{
		ID:     fmt.Sprintf("conv-%d", time.Now().UnixNano()),
		Vector: emb,
		Payload: map[string]any{
			"text":      content,
			"project":   project,
			"type":      "conversation",
			"timestamp": time.Now().UTC().Format(time.RFC3339),
		},
	}
	collection := CollectionName(project)
	if err := s.EnsureCollection(ctx, collection); err != nil {
		return err
	}
	return s.Upsert(ctx, collection, []Point{point})
}

// collectionExists reports whether a collection is already present.
func (s *Service) collectionExists(ctx context.Context, name string) bool {
	list, err := s.ListCollections(ctx)
	if err != nil {
		return false
	}
	for _, c := range list {
		if c == name {
			return true
		}
	}
	return false
}

// embedText uses the shared embedding endpoint (nvidia/openai style).
func (s *Service) embedText(ctx context.Context, text string) []float32 {
	// The gateway keeps a single embedding call surface: hit NVIDIA's
	// /embeddings endpoint with the default provider key when configured.
	// Deliberately fails soft: without a key we skip enrichment entirely.
	return embedViaProvider(ctx, text)
}

// StoreEntry saves a single memory item.
func (s *Service) StoreEntry(ctx context.Context, project, text, file, typ string, metadata map[string]any) error {
	if project == "" || text == "" {
		return nil
	}
	if typ == "" {
		typ = "general"
	}
	collection := CollectionName(project)
	if err := s.EnsureCollection(ctx, collection); err != nil {
		return err
	}
	vec := embedViaProvider(ctx, text)
	if len(vec) == 0 {
		return nil // no embedding backend configured — silently skip
	}
	payload := map[string]any{
		"text":      text,
		"project":   project,
		"file":      file,
		"type":      typ,
		"timestamp": time.Now().UTC().Format(time.RFC3339),
	}
	for k, v := range metadata {
		if _, exists := payload[k]; !exists {
			payload[k] = v
		}
	}
	return s.Upsert(ctx, collection, []Point{{
		ID:      fmt.Sprintf("mem-%d", time.Now().UnixNano()),
		Vector:  vec,
		Payload: payload,
	}})
}

// SearchProject runs the memory search used by /api/memory/search.
func (s *Service) SearchProject(ctx context.Context, project, query string, topK int) ([]SearchResult, error) {
	if topK <= 0 {
		topK = 10
	}
	collection := CollectionName(project)
	vec := embedViaProvider(ctx, query)
	if len(vec) == 0 {
		return nil, nil
	}
	points, err := s.Search(ctx, collection, vec, topK, 0.5)
	if err != nil {
		return nil, err
	}
	return pointsToResults(points), nil
}

// ListProject returns every memory stored under a project.
func (s *Service) ListProject(ctx context.Context, project string, limit int) ([]SearchResult, error) {
	if limit <= 0 {
		limit = 200
	}
	collection := CollectionName(project)
	// Scroll-style retrieve: Qdrant returns Scroll result with "points"
	resp, err := s.req(ctx, "POST", fmt.Sprintf("/collections/%s/points/scroll", collection), map[string]any{
		"limit": limit, "with_payload": true, "with_vector": false,
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("scroll failed: %d", resp.StatusCode)
	}
	var out struct {
		Result struct {
			Points []struct {
				ID      any            `json:"id"`
				Payload map[string]any `json:"payload"`
			} `json:"points"`
		} `json:"result"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	items := make([]SearchResult, 0, len(out.Result.Points))
	for _, p := range out.Result.Points {
		items = append(items, SearchResult{
			ID:      fmt.Sprint(p.ID),
			Text:    asString(p.Payload["text"]),
			Project: asString(p.Payload["project"]),
			Type:    asString(p.Payload["type"]),
			File:    asString(p.Payload["file"]),
		})
	}
	return items, nil
}

// ListProjects returns the distinct project names that have collections.
func (s *Service) ListProjects(ctx context.Context) ([]map[string]any, error) {
	cols, err := s.ListCollections(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]map[string]any, 0, len(cols))
	for _, c := range cols {
		if !strings.HasPrefix(c, "project_") {
			continue
		}
		name := strings.TrimPrefix(c, "project_")
		stats, _ := s.projectStatsDirect(ctx, c)
		m := map[string]any{"name": name}
		for k, v := range stats {
			m[k] = v
		}
		out = append(out, m)
	}
	return out, nil
}

// ProjectStats returns summary stats for one project.
func (s *Service) ProjectStats(ctx context.Context, project string) (map[string]any, error) {
	collection := CollectionName(project)
	return s.projectStatsDirect(ctx, collection)
}

func (s *Service) projectStatsDirect(ctx context.Context, collection string) (map[string]any, error) {
	resp, err := s.req(ctx, "GET", "/collections/"+collection, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("project not found")
	}
	var out struct {
		Result struct {
			PointsCount int `json:"points_count"`
			VectorsCount int `json:"vectors_count"`
		} `json:"result"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&out)
	return map[string]any{
		"name":         strings.TrimPrefix(collection, "project_"),
		"memory_count": out.Result.PointsCount,
		"status":       "active",
	}, nil
}

// DeleteProject drops the project's collection.
func (s *Service) DeleteProject(ctx context.Context, project string) error {
	return s.DeleteCollection(ctx, CollectionName(project))
}

func asString(v any) string {
	switch t := v.(type) {
	case string:
		return t
	case fmt.Stringer:
		return t.String()
	default:
		return ""
	}
}

// CollectionName derives the Qdrant collection name for a project.
func CollectionName(project string) string {
	safe := strings.Map(func(r rune) rune {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '_' {
			return r
		}
		return '_'
	}, strings.ToLower(project))
	return "project_" + safe
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

// memoryResponse wraps a search result for the API layer.
type SearchResult struct {
	ID      string         `json:"id"`
	Text    string         `json:"text"`
	Project string         `json:"project"`
	Type    string         `json:"type"`
	Score   float64        `json:"score"`
	File    string         `json:"file,omitempty"`
	Payload map[string]any `json:"-"`
}

func pointsToResults(points []Point) []SearchResult {
	out := make([]SearchResult, 0, len(points))
	for _, p := range points {
		r := SearchResult{
			ID:    p.ID,
			Score: p.Score,
		}
		if t, ok := p.Payload["text"].(string); ok {
			r.Text = t
		}
		if t, ok := p.Payload["project"].(string); ok {
			r.Project = t
		}
		if t, ok := p.Payload["type"].(string); ok {
			r.Type = t
		}
		if t, ok := p.Payload["file"].(string); ok {
			r.File = t
		}
		out = append(out, r)
	}
	return out
}
