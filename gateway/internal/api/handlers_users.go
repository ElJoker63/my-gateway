package api

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"github.com/ElJoker63/my-gateway/gateway/internal/keymanager"
	"github.com/ElJoker63/my-gateway/gateway/internal/users"
)

// ---------- Admin: user CRUD (master key only) ----------

func (s *Server) handleAdminListUsers(w http.ResponseWriter, r *http.Request) {
	if !s.isMaster(r) {
		s.writeError(w, http.StatusForbidden, "admin only")
		return
	}
	if s.users == nil {
		s.writeError(w, http.StatusServiceUnavailable, "users store unavailable")
		return
	}
	list := s.users.List(r.Context())
	out := make([]map[string]any, 0, len(list))
	for _, u := range list {
		out = append(out, u.Public())
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"users": out, "total": len(out)})
}

func (s *Server) handleAdminCreateUser(w http.ResponseWriter, r *http.Request) {
	if !s.isMaster(r) {
		s.writeError(w, http.StatusForbidden, "admin only")
		return
	}
	if s.users == nil {
		s.writeError(w, http.StatusServiceUnavailable, "users store unavailable")
		return
	}
	var body struct {
		Name   string `json:"name"`
		Email  string `json:"email"`
		Admin  bool   `json:"is_admin"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Name) == "" {
		s.writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	u, rawKey, err := s.users.Create(r.Context(), strings.TrimSpace(body.Name), strings.TrimSpace(body.Email), body.Admin)
	if err != nil {
		s.writeError(w, http.StatusInternalServerError, "user creation failed")
		return
	}

	// Show the key exactly once — after that only the hash + masked display remain.
	s.writeJSON(w, http.StatusCreated, map[string]any{
		"user":     u.Public(),
		"api_key":  rawKey, // handle with care — not retrievable later
		"_note":    "The API key is shown once and never stored.",
	})
}

func (s *Server) handleAdminGetUser(w http.ResponseWriter, r *http.Request) {
	if !s.isMaster(r) {
		s.writeError(w, http.StatusForbidden, "admin only")
		return
	}
	u, ok := s.users.Get(r.Context(), chi.URLParam(r, "id"))
	if !ok {
		s.writeError(w, http.StatusNotFound, "user not found")
		return
	}
	s.writeJSON(w, http.StatusOK, u.Public())
}

func (s *Server) handleAdminDeleteUser(w http.ResponseWriter, r *http.Request) {
	if !s.isMaster(r) {
		s.writeError(w, http.StatusForbidden, "admin only")
		return
	}
	targetID := chi.URLParam(r, "id")
	u, ok := s.users.Get(r.Context(), targetID)
	if !ok {
		s.writeError(w, http.StatusNotFound, "user not found")
		return
	}
	if u.IsAdmin {
		s.writeError(w, http.StatusBadRequest, "cannot delete the admin user")
		return
	}
	// We don't physically delete — mark disabled so existing keys stop working.
	if err := s.users.Disable(r.Context(), targetID); err != nil {
		s.writeError(w, http.StatusInternalServerError, "disable failed")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"disabled": targetID})
}

func (s *Server) handleAdminRotateUserKey(w http.ResponseWriter, r *http.Request) {
	if !s.isMaster(r) {
		s.writeError(w, http.StatusForbidden, "admin only")
		return
	}
	targetID := chi.URLParam(r, "id")
	newKey, err := s.users.RotateKey(r.Context(), targetID)
	if err != nil {
		s.writeError(w, http.StatusNotFound, "user not found")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"id": targetID, "api_key": newKey})
}

// ---------- Self-service: current user ----------

func (s *Server) handleMe(w http.ResponseWriter, r *http.Request) {
	userID := requestUserID(r.Context())
	if userID == "" {
		s.writeError(w, http.StatusForbidden, "user key required (gwu_*)")
		return
	}
	u, ok := s.users.Get(r.Context(), userID)
	if !ok {
		s.writeError(w, http.StatusNotFound, "user not found")
		return
	}
	s.writeJSON(w, http.StatusOK, u.Public())
}

func (s *Server) handleMeUsage(w http.ResponseWriter, r *http.Request) {
	userID := requestUserID(r.Context())
	if userID == "" {
		s.writeError(w, http.StatusForbidden, "user key required")
		return
	}
	// Scopes to the user's pools only — they don't see anyone else's keys.
	out := map[string]any{}
	if s.keys != nil {
		for _, name := range s.keys.Providers() {
			if pool := s.keys.Pool(userID, name); pool != nil {
				out[name] = poolStatus(s, userID, name)
			}
		}
	}
	s.writeJSON(w, http.StatusOK, out)
}

// ---------- Helpers ----------

// isMaster is true when the caller used the master key (system tenant).
func (s *Server) isMaster(r *http.Request) bool {
	return requestTenant(r.Context()) == "" ||
		requestTenant(r.Context()) == keymanager.TenantSystem
}

var _ = users.KeyPrefix
