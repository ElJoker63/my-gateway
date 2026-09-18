package api

import (
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/go-chi/chi/v5"
)

// getEnvDefault returns an env var or a fallback.
func getEnvDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// timeUntil converts a deadline to remaining duration.
func timeUntil(t time.Time) time.Duration { return time.Until(t) }

// mountDashboard serves the built Vue SPA from ../dashboard/dist.
func (s *Server) mountDashboard(mux *chi.Mux) {
	dist := os.Getenv("DASHBOARD_DIST")
	if dist == "" {
		// Walk up from internal/api to reach the dashboard/dist path
		wd, err := os.Getwd()
		if err == nil {
			candidates := []string{
				filepath.Join(wd, "..", "..", "app", "dashboard", "dist"),
				filepath.Join(wd, "app", "dashboard", "dist"),
				filepath.Join(wd, "dist"),
			}
			for _, c := range candidates {
				if st, err := os.Stat(c); err == nil && st.IsDir() {
					dist = c
					break
				}
			}
		}
	}
	if dist == "" {
		slog.Warn("dashboard dist not found — /dashboard will 404")
		return
	}
	fs := http.FileServer(http.Dir(dist))
	mux.Handle("/dashboard/*", http.StripPrefix("/dashboard/", fs))
	mux.Handle("/dashboard", http.RedirectHandler("/dashboard/", http.StatusFound))
}
