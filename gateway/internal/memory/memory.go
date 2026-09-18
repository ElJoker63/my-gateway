// Package memory implements Qdrant-backed vector memory for the gateway.
package memory

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Point is one stored memory.
type Point struct {
	ID      string            `json:"id"`
	Vector  []float32         `json:"vector,omitempty"`
	Payload map[string]any    `json:"payload"`
	Score   float64           `json:"score,omitempty"`
}

// Service is the Qdrant HTTP client wrapper.
type Service struct {
	host string
	port int
	key  string
	http *http.Client
	dim  int
}

// New builds a memory service pointing at the Qdrant REST endpoint.
func New(host string, port int, apiKey string, dim int) *Service {
	if host == "" {
		host = "localhost"
	}
	if port <= 0 {
		port = 6333
	}
	return &Service{
		host: host,
		port: port,
		key:  apiKey,
		dim:  dim,
		http: &http.Client{Timeout: 10 * time.Second},
	}
}

// base is the Qdrant base URL.
func (s *Service) base() string { return fmt.Sprintf("http://%s:%d", s.host, s.port) }

func (s *Service) req(ctx context.Context, method, path string, body any) (*http.Response, error) {
	var rd io.Reader
	if body != nil {
		buf, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		rd = bytes.NewReader(buf)
	}
	req, err := http.NewRequestWithContext(ctx, method, s.base()+path, rd)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	if s.key != "" {
		req.Header.Set("api-key", s.key)
	}
	return s.http.Do(req)
}

// EnsureCollection creates a collection if missing.
func (s *Service) EnsureCollection(ctx context.Context, name string) error {
	resp, err := s.req(ctx, http.MethodGet, "/collections/"+name, nil)
	if err != nil {
		return err
	}
	resp.Body.Close()
	if resp.StatusCode == 200 {
		return nil
	}

	body := map[string]any{
		"vectors": map[string]any{
			"size":     s.dim,
			"distance": "Cosine",
		},
	}
	resp, err = s.req(ctx, http.MethodPut, "/collections/"+name, body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return fmt.Errorf("create collection failed (%d): %s", resp.StatusCode, string(raw))
	}
	return nil
}

// Upsert stores a batch of points.
func (s *Service) Upsert(ctx context.Context, collection string, points []Point) error {
	if len(points) == 0 {
		return nil
	}
	body := map[string]any{"points": points}
	resp, err := s.req(ctx, http.MethodPut, fmt.Sprintf("/collections/%s/points?wait=true", collection), body)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return fmt.Errorf("upsert failed (%d): %s", resp.StatusCode, string(raw))
	}
	return nil
}

// Search runs a nearest-neighbors query.
func (s *Service) Search(ctx context.Context, collection string, vector []float32, limit int, threshold float64) ([]Point, error) {
	body := map[string]any{
		"vector":          vector,
		"limit":           limit,
		"with_payload":     true,
		"score_threshold": threshold,
	}
	resp, err := s.req(ctx, http.MethodPost, fmt.Sprintf("/collections/%s/points/search", collection), body)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return nil, fmt.Errorf("search failed (%d): %s", resp.StatusCode, string(raw))
	}
	var out struct {
		Result []struct {
			ID      any             `json:"id"`
			Score   float64         `json:"score"`
			Payload map[string]any  `json:"payload"`
		} `json:"result"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	points := make([]Point, 0, len(out.Result))
	for _, p := range out.Result {
		points = append(points, Point{
			ID:      fmt.Sprint(p.ID),
			Score:   p.Score,
			Payload: p.Payload,
		})
	}
	return points, nil
}

// ListCollections returns all project_* collection names.
func (s *Service) ListCollections(ctx context.Context) ([]string, error) {
	resp, err := s.req(ctx, http.MethodGet, "/collections", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var out struct {
		Result struct {
			Collections []struct {
				Name string `json:"name"`
			} `json:"collections"`
		} `json:"result"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	names := make([]string, 0, len(out.Result.Collections))
	for _, c := range out.Result.Collections {
		names = append(names, c.Name)
	}
	return names, nil
}

// DeleteCollection drops a project collection.
func (s *Service) DeleteCollection(ctx context.Context, name string) error {
	resp, err := s.req(ctx, http.MethodDelete, "/collections/"+name, nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 && resp.StatusCode != 404 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<10))
		return fmt.Errorf("delete failed (%d): %s", resp.StatusCode, string(raw))
	}
	return nil
}

// Health pings Qdrant.
func (s *Service) Health(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	resp, err := s.req(ctx, http.MethodGet, "/readyz", nil)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == 200
}
