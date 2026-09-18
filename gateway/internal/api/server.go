// Package api wires the HTTP server: chi router, middleware, and handlers.
package api

import (
	"encoding/json"
	"log"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"

	"github.com/ElJoker63/my-gateway/gateway/internal/breaker"
	"github.com/ElJoker63/my-gateway/gateway/internal/cache"
	"github.com/ElJoker63/my-gateway/gateway/internal/combos"
	"github.com/ElJoker63/my-gateway/gateway/internal/config"
	"github.com/ElJoker63/my-gateway/gateway/internal/keymanager"
	"github.com/ElJoker63/my-gateway/gateway/internal/memory"
	"github.com/ElJoker63/my-gateway/gateway/internal/metrics"
	"github.com/ElJoker63/my-gateway/gateway/internal/oauth"
	"github.com/ElJoker63/my-gateway/gateway/internal/providers"
)

// Server is the gateway HTTP app.
type Server struct {
	cfg       *config.Settings
	keys      *keymanager.Manager
	breaker   *breaker.Breaker
	cache     *cache.Store
	metrics   *metrics.Store
	combos    *combos.Store
	oauthMgr  *oauth.Manager
	memoryMgr *memory.Service
	providers map[string]providers.Provider
	router    *chi.Mux
	startedAt time.Time
}

// NewServer builds the wired gateway.
func NewServer(cfg *config.Settings) (*Server, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}

	// Providers are constructed even without keys — they fail at call time.
	prov := map[string]providers.Provider{}
	for name := range config.ProviderNames() {
		_ = name // iterate for ordering only; lookup uses the map below
	}
	for _, name := range config.ProviderNames() {
		pcfg := providers.ProviderConfig{
			AllowedRoots: cfg.AllowedIndexRoots,
			Logger:       slog.Default(),
			Overrides:    *cfg,
		}
		if keys := cfg.KeysFor(name); len(keys) > 0 {
			pcfg.APIKey = keys[0]
		}
		p, err := providers.RegistryDefault.NewProvider(name, pcfg)
		if err != nil {
			slog.Warn("provider init failed", "name", name, "err", err)
			continue
		}
		prov[name] = p
	}

	s := &Server{
		cfg:       cfg,
		providers: prov,
		metrics:   metrics.Global(),
		startedAt: time.Now(),
	}

	s.router = chi.NewRouter()
	s.mount()
	return s, nil
}

// AttachInfra wires the heavier services after the server exists.
func (s *Server) AttachInfra(
	keys *keymanager.Manager,
	c *cache.Store,
	cb *combos.Store,
	om *oauth.Manager,
	mem *memory.Service,
	br *breaker.Breaker,
) {
	s.keys = keys
	s.cache = c
	s.combos = cb
	s.oauthMgr = om
	s.memoryMgr = mem
	s.breaker = br
}

// ServeHTTP makes Server implement http.Handler.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.router.ServeHTTP(w, r)
}

// mount sets up middlewares and all routes.
func (s *Server) mount() {
	r := s.router

	// Middlewares
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(180 * time.Second))
	r.Use(s.timingMiddleware)
	r.Use(s.bodyLimitMiddleware)
	r.Use(s.corsMiddleware)
	r.Use(s.authMiddleware)

	// Root redirects to dashboard (keeps the DX nice).
	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/dashboard/", http.StatusFound)
	})

	// Health (public).
	r.Get("/health", s.handleHealth)

	// System metrics
	r.Route("/api", func(r chi.Router) {
		r.Get("/metrics", s.handleMetrics)
		r.Get("/cache/stats", s.handleCacheStats)
		r.Get("/keys/status", s.handleKeysStatus)
		r.Get("/rate-limit", s.handleRateLimitStatus) // legacy alias
		r.Post("/providers/{name}/keys", s.handleAddProviderKey)

		// Memory
		r.Post("/memory/store", s.handleMemoryStore)
		r.Post("/memory/search", s.handleMemorySearch)
		r.Get("/memory/project/{project}", s.handleMemoryListProject)
		r.Delete("/memory/project/{project}", s.handleMemoryDeleteProject)

		// Projects
		r.Post("/projects/index", s.handleIndexProject)
		r.Get("/projects", s.handleProjectsList)
		r.Get("/projects/{name}", s.handleProjectGet)
		r.Delete("/projects/{name}", s.handleProjectDelete)

		// Combos
		r.Get("/combos", s.handleCombosList)
		r.Post("/combos", s.handleCombosPut)
		r.Get("/combos/{name}", s.handleCombosGet)
		r.Delete("/combos/{name}", s.handleCombosDelete)

		// OAuth (kiro / antigravity)
		r.Post("/oauth/{provider}/start", s.handleOAuthStart)
		r.Get("/oauth/{provider}/poll", s.handleOAuthPoll)
		r.Get("/oauth/{provider}/callback", s.handleOAuthCallback)
		r.Get("/oauth/status", s.handleOAuthStatus)
		r.Delete("/oauth/{provider}", s.handleOAuthDisconnect)
	})

	// Chat endpoints
	r.Route("/v1", func(r chi.Router) {
		r.Post("/chat/completions", s.handleChat)
		r.Post("/messages", s.handleAnthropicChat)
	})
	r.Post("/api/chat", s.handleGatewayChat)
	r.Post("/response", s.handleChat) // alias used by some agents

	// Static dashboard
	s.mountDashboard(r)
}

// -------------------- Middleware --------------------

// timingMiddleware adds the X-Response-Time header.
func (s *Server) timingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		w.Header().Set("X-Response-Time", time.Since(start).String())
	})
}

// bodyLimitMiddleware rejects oversized request bodies before parsing.
func (s *Server) bodyLimitMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		max := int64(s.cfg.MaxRequestMB) * 1024 * 1024
		if r.ContentLength > max {
			s.writeError(w, http.StatusRequestEntityTooLarge, "request body exceeds the configured limit")
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, max)
		next.ServeHTTP(w, r)
	})
}

// corsMiddleware applies the allowed origins from settings.
func (s *Server) corsMiddleware(next http.Handler) http.Handler {
	return cors.Handler(cors.Options{
		AllowedOrigins:   s.cfg.CORSOrigins,
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"*"},
		AllowCredentials: true,
		MaxAge:           300,
	})(next)
}

// authMiddleware enforces the gateway API key for protected routes.
func (s *Server) authMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Public routes
		public := map[string]bool{"/": true, "/health": true}
		if public[r.URL.Path] || strings.HasPrefix(r.URL.Path, "/dashboard/") {
			next.ServeHTTP(w, r)
			return
		}

		if !s.cfg.AuthEnabled() {
			next.ServeHTTP(w, r)
			return
		}

		key := bearerToken(r)
		if key == "" {
			key = r.Header.Get("X-API-Key")
		}
		if key == "" || key != s.cfg.GatewayAPIKey {
			s.writeError(w, http.StatusUnauthorized, "Invalid or missing API key")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func bearerToken(r *http.Request) string {
	h := r.Header.Get("Authorization")
	if !strings.HasPrefix(h, "Bearer ") {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(h, "Bearer "))
}

// -------------------- Helpers --------------------

func (s *Server) writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		slog.Warn("json encode failed", "err", err)
	}
}

func (s *Server) writeError(w http.ResponseWriter, status int, msg string) {
	s.writeJSON(w, status, map[string]any{"error": msg})
}

// log helpers
var _ = log.Print
