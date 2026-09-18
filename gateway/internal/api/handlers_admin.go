package api

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"github.com/ElJoker63/my-gateway/gateway/internal/combos"
	"github.com/ElJoker63/my-gateway/gateway/internal/indexer"
)

// ---------- Memory handlers ----------

type memoryStoreRequest struct {
	Text     string         `json:"text"`
	Project  string         `json:"project"`
	File     string         `json:"file,omitempty"`
	Type     string         `json:"type,omitempty"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

type memorySearchRequest struct {
	Query   string `json:"query"`
	Project string `json:"project,omitempty"`
	Type    string `json:"type,omitempty"`
	TopK    int    `json:"top_k,omitempty"`
}

func (s *Server) handleMemoryStore(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	var body memoryStoreRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Text == "" || body.Project == "" {
		s.writeError(w, http.StatusBadRequest, "text and project are required")
		return
	}
	typ := body.Type
	if typ == "" {
		typ = "general"
	}
	if err := s.memoryMgr.StoreEntry(r.Context(), body.Project, body.Text, body.File, typ, body.Metadata); err != nil {
		s.writeError(w, http.StatusInternalServerError, "failed to store memory")
		return
	}
	s.writeJSON(w, http.StatusCreated, map[string]any{"status": "stored"})
}

func (s *Server) handleMemorySearch(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	var body memorySearchRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	topK := body.TopK
	if topK <= 0 {
		topK = 10
	}
	results, err := s.memoryMgr.SearchProject(r.Context(), body.Project, body.Query, topK)
	if err != nil {
		s.writeError(w, http.StatusInternalServerError, "search failed")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"results": results})
}

func (s *Server) handleMemoryListProject(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	project := chi.URLParam(r, "project")
	items, err := s.memoryMgr.ListProject(r.Context(), project, 200)
	if err != nil {
		s.writeError(w, http.StatusInternalServerError, "could not list project memory")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"project": project, "memories": items})
}

func (s *Server) handleMemoryDeleteProject(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	project := chi.URLParam(r, "project")
	if err := s.memoryMgr.DeleteProject(r.Context(), project); err != nil {
		s.writeError(w, http.StatusInternalServerError, "could not delete project")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"status": "deleted", "project": project})
}

// ---------- Projects handlers ----------

type indexProjectRequest struct {
	Path         string   `json:"path"`
	ProjectName  string   `json:"project_name,omitempty"`
	FilePatterns []string `json:"file_patterns,omitempty"`
}

func (s *Server) handleIndexProject(w http.ResponseWriter, r *http.Request) {
	var body indexProjectRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if strings.TrimSpace(body.Path) == "" {
		s.writeError(w, http.StatusBadRequest, "path is required")
		return
	}
	if len(s.cfg.AllowedIndexRoots) == 0 {
		s.writeError(w, http.StatusForbidden, "indexing is disabled (ALLOWED_INDEX_ROOTS is empty)")
		return
	}
	if !pathWithinRoots(body.Path, s.cfg.AllowedIndexRoots) {
		s.writeError(w, http.StatusForbidden, "path is outside the allowed index roots")
		return
	}
	name := body.ProjectName
	if name == "" {
		name = lastPathComponent(body.Path)
	}

	// The actual indexing runs in the background; the response is immediate
	// because this is a long-running job on the filesystem.
	ix := s.projectIndexer()
	go func() {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		res, err := ix.Run(ctx, indexer.Options{Path: body.Path, Project: name, FilePatterns: body.FilePatterns})
		if err != nil {
			slog.Warn("project indexing failed", "project", name, "err", err)
			return
		}
		slog.Info("project indexed", "project", name, "memories", res.Memories, "files", res.FilesScanned)
	}()

	s.writeJSON(w, http.StatusAccepted, map[string]any{
		"status":  "indexing_started",
		"project": name,
		"path":    body.Path,
	})
}

func (s *Server) handleProjectsList(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	projects, err := s.memoryMgr.ListProjects(r.Context())
	if err != nil {
		s.writeError(w, http.StatusInternalServerError, "failed to list projects")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"projects": projects, "total": len(projects)})
}

func (s *Server) handleProjectGet(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	name := chi.URLParam(r, "name")
	stats, err := s.memoryMgr.ProjectStats(r.Context(), name)
	if err != nil {
		s.writeError(w, http.StatusNotFound, "project not found")
		return
	}
	s.writeJSON(w, http.StatusOK, stats)
}

func (s *Server) handleProjectDelete(w http.ResponseWriter, r *http.Request) {
	if s.memoryMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "memory service unavailable")
		return
	}
	name := chi.URLParam(r, "name")
	if err := s.memoryMgr.DeleteProject(r.Context(), name); err != nil {
		s.writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"status": "deleted", "project": name})
}

// ---------- Combo handlers ----------

type comboInput struct {
	Name     string          `json:"name"`
	Targets  []combos.Target `json:"targets"`
	Strategy string          `json:"strategy"`
	RaceSize int             `json:"race_size"`
}

func (s *Server) handleCombosList(w http.ResponseWriter, r *http.Request) {
	if s.combos == nil {
		s.writeError(w, http.StatusServiceUnavailable, "combos store unavailable")
		return
	}
	list := s.combos.List(r.Context())
	s.writeJSON(w, http.StatusOK, map[string]any{"combos": list, "total": len(list)})
}

func (s *Server) handleCombosPut(w http.ResponseWriter, r *http.Request) {
	if s.combos == nil {
		s.writeError(w, http.StatusServiceUnavailable, "combos store unavailable")
		return
	}
	var body comboInput
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		s.writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if body.Name == "" || len(body.Targets) == 0 {
		s.writeError(w, http.StatusBadRequest, "name and at least one target are required")
		return
	}
	c := &combos.Combo{
		Name:     body.Name,
		Targets:  body.Targets,
		Strategy: body.Strategy,
		RaceSize: body.RaceSize,
	}
	if err := s.combos.Save(r.Context(), c); err != nil {
		s.writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	s.writeJSON(w, http.StatusCreated, c)
}

func (s *Server) handleCombosGet(w http.ResponseWriter, r *http.Request) {
	if s.combos == nil {
		s.writeError(w, http.StatusServiceUnavailable, "combos store unavailable")
		return
	}
	c, ok := s.combos.Get(r.Context(), chi.URLParam(r, "name"))
	if !ok {
		s.writeError(w, http.StatusNotFound, "combo not found")
		return
	}
	s.writeJSON(w, http.StatusOK, c)
}

func (s *Server) handleCombosDelete(w http.ResponseWriter, r *http.Request) {
	if s.combos == nil {
		s.writeError(w, http.StatusServiceUnavailable, "combos store unavailable")
		return
	}
	if !s.combos.Delete(r.Context(), chi.URLParam(r, "name")) {
		s.writeError(w, http.StatusNotFound, "combo not found")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"status": "deleted"})
}

// ---------- Admin handlers ----------

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	services := map[string]any{"gateway": map[string]any{"status": "healthy"}}
	if s.memoryMgr != nil {
		services["qdrant"] = map[string]any{"status": conditionalStatus(s.memoryMgr.Health(r.Context()))}
	}
	s.writeJSON(w, http.StatusOK, map[string]any{
		"status":   "healthy",
		"services": services,
		"version":  "1.1.0",
	})
}

func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	sum := s.metrics.Summary()
	if s.breaker != nil {
		sum["circuit_states"] = s.breaker.Snapshot()
	}
	s.writeJSON(w, http.StatusOK, sum)
}

func (s *Server) handleCacheStats(w http.ResponseWriter, r *http.Request) {
	if s.cache == nil {
		s.writeJSON(w, http.StatusOK, map[string]any{"hits": 0, "misses": 0})
		return
	}
	s.writeJSON(w, http.StatusOK, s.cache.Stats(r.Context()))
}

func (s *Server) handleKeysStatus(w http.ResponseWriter, r *http.Request) {
	tenant := requestTenant(r.Context())
	provider := r.URL.Query().Get("provider")
	if provider == "" {
		if s.keys == nil {
			s.writeJSON(w, http.StatusOK, map[string]any{})
			return
		}
		out := map[string]any{}
		for _, name := range s.keys.Providers() {
			out[name] = poolStatus(s, tenant, name)
		}
		s.writeJSON(w, http.StatusOK, out)
		return
	}
	if s.keys == nil {
		s.writeError(w, http.StatusNotFound, "provider not found")
		return
	}
	s.writeJSON(w, http.StatusOK, poolStatus(s, tenant, provider))
}

func (s *Server) handleRateLimitStatus(w http.ResponseWriter, r *http.Request) {
	s.handleKeysStatus(w, r)
}

func (s *Server) handleAddProviderKey(w http.ResponseWriter, r *http.Request) {
	if s.keys == nil {
		s.writeError(w, http.StatusServiceUnavailable, "key manager unavailable")
		return
	}
	name := chi.URLParam(r, "name")
	var body struct {
		Key string `json:"key"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Key) == "" {
		s.writeError(w, http.StatusBadRequest, "key is required")
		return
	}
	tenant := requestTenant(r.Context())
	if !s.keys.AddKey(tenant, name, strings.TrimSpace(body.Key)) {
		s.writeError(w, http.StatusBadRequest, "key already exists")
		return
	}
	s.writeJSON(w, http.StatusCreated, map[string]any{"provider": name, "status": "added"})
}

// ---------- small helpers ----------

func conditionalStatus(ok bool) string {
	if ok {
		return "healthy"
	}
	return "unhealthy"
}

func poolStatus(s *Server, tenant string, provider string) map[string]any {
	pool := s.keys.Pool(tenant, provider)
	if pool == nil {
		return map[string]any{
			"provider":       provider,
			"total_keys":     0,
			"available_keys": 0,
			"keys":           []any{},
		}
	}
	keys := make([]map[string]any, 0, len(pool.Keys))
	for _, k := range pool.Keys {
		keys = append(keys, map[string]any{
			"id":             k.Fingerprint,
			"display":        k.Display,
			"index":          k.Index,
			"requests_used":  k.RequestsUsed,
			"requests_limit": k.RequestsLimit,
			"status":         "active",
		})
	}
	return map[string]any{
		"provider":       provider,
		"total_keys":     len(pool.Keys),
		"available_keys": len(pool.Keys),
		"rpm_per_key":    pool.RPMPerKey,
		"keys":           keys,
	}
}

func lastPathComponent(p string) string {
	p = strings.TrimRight(p, "/\\")
	if i := strings.LastIndexAny(p, "/\\"); i >= 0 {
		return p[i+1:]
	}
	return p
}

func pathWithinRoots(path string, roots []string) bool {
	if len(roots) == 0 {
		return false
	}
	norm := strings.ReplaceAll(path, "\\", "/")
	for _, root := range roots {
		normalized := strings.ReplaceAll(strings.TrimSuffix(strings.TrimSpace(root), "/"), "\\", "/")
		if normalized == "" {
			continue
		}
		if norm == normalized || strings.HasPrefix(norm, normalized+"/") {
			return true
		}
	}
	return false
}
