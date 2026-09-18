// Embedding helpers — single shared code path for local/remote embedding.
package memory

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
)

// EmbedBatch generates embeddings for multiple texts (one API call when the
// provider supports array input; NVIDIA's /embeddings does).
func EmbedBatch(ctx context.Context, texts []string) [][]float32 {
	if len(texts) == 0 {
		return nil
	}
	key := os.Getenv("NVIDIA_API_KEY")
	if key == "" {
		return nil
	}
	base := os.Getenv("NVIDIA_BASE_URL")
	if base == "" {
		base = "https://integrate.api.nvidia.com/v1"
	}
	model := os.Getenv("EMBEDDING_MODEL_NAME")
	if model == "" {
		model = "nvidia/nv-embedqa-e5-v5"
	}

	body := map[string]any{"input": texts, "model": model, "encoding_format": "float"}
	buf, _ := json.Marshal(body)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/embeddings", bytes.NewReader(buf))
	if err != nil {
		return nil
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		io.Copy(io.Discard, resp.Body)
		return nil
	}

	var payload struct {
		Data []struct {
			Index     int        `json:"index"`
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil
	}
	if len(payload.Data) != len(texts) {
		return nil
	}
	out := make([][]float32, len(payload.Data))
	for _, item := range payload.Data {
		out[item.Index] = item.Embedding
	}
	return out
}

// embedViaProvider calls the configured embedding endpoint.
// Reads NVIDIA_API_KEY and NVIDIA_BASE_URL from env (local sentinel model is
// the Python-only fallback; in the Go build embeddings are remote-only).
func embedViaProvider(ctx context.Context, text string) []float32 {
	key := os.Getenv("NVIDIA_API_KEY")
	if key == "" {
		return nil
	}
	base := os.Getenv("NVIDIA_BASE_URL")
	if base == "" {
		base = "https://integrate.api.nvidia.com/v1"
	}
	model := os.Getenv("EMBEDDING_MODEL_NAME")
	if model == "" {
		model = "nvidia/nv-embedqa-e5-v5"
	}

	body := map[string]any{"input": text, "model": model, "encoding_format": "float"}
	buf, _ := json.Marshal(body)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, base+"/embeddings", bytes.NewReader(buf))
	if err != nil {
		return nil
	}
	req.Header.Set("Authorization", "Bearer "+key)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		io.Copy(io.Discard, resp.Body)
		return nil
	}

	var payload struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil
	}
	if len(payload.Data) == 0 {
		return nil
	}
	return payload.Data[0].Embedding
}

// embedViaProvider kept for single-text paths
