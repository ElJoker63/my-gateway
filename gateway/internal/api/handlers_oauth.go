package api

import (
	"net/http"

	"github.com/go-chi/chi/v5"

	"github.com/ElJoker63/my-gateway/gateway/internal/oauth"
)

// ---------- OAuth handlers ----------

func (s *Server) handleOAuthStart(w http.ResponseWriter, r *http.Request) {
	if s.oauthMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "oauth not available")
		return
	}
	provider := chi.URLParam(r, "provider")

	switch provider {
	case "kiro":
		// AWS SSO OIDC device code
		out, err := s.oauthMgr.StartDeviceCode(oauth.DeviceCodeSpec{
			Provider: "kiro",
			OIDCBase: "https://oidc.us-east-1.amazonaws.com",
			Scopes: []string{
				"codewhisperer:completions",
				"codewhisperer:analysis",
				"codewhisperer:conversations",
			},
		})
		if err != nil {
			s.writeError(w, http.StatusBadGateway, "kiro device flow start failed: "+err.Error())
			return
		}
		s.writeJSON(w, http.StatusOK, out)
		return

	case "antigravity":
		// Google PKCE — the flow normally needs a reachable callback URL. The
		// dashboard's /oauth/callback route serves as the redirect target.
		callback := "http://localhost:8000/dashboard/oauth/callback"
		authURL, state, err := s.oauthMgr.StartPKCE(oauth.PKCESpec{
			Name:         "antigravity",
			ClientID:     getEnvDefault("ANTIGRAVITY_CLIENT_ID", "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"),
			ClientSecret: getEnvDefault("ANTIGRAVITY_CLIENT_SECRET", ""),
			AuthorizeURL: "https://accounts.google.com/o/oauth2/v2/auth",
			TokenURL:     "https://oauth2.googleapis.com/token",
			RedirectURI:  callback,
			Scopes: []string{
				"openid",
				"https://www.googleapis.com/auth/cloud-platform",
				"https://www.googleapis.com/auth/userinfo.email",
				"https://www.googleapis.com/auth/userinfo.profile",
				"https://www.googleapis.com/auth/cclog",
				"https://www.googleapis.com/auth/experimentsandconfigs",
			},
		})
		if err != nil {
			s.writeError(w, http.StatusBadGateway, err.Error())
			return
		}
		s.writeJSON(w, http.StatusOK, map[string]any{
			"provider": "antigravity",
			"flow":     "pkce",
			"authUrl":  authURL,
			"state":    state,
		})
		return

	default:
		s.writeError(w, http.StatusNotFound, "unknown OAuth provider: "+provider)
		return
	}
}

func (s *Server) handleOAuthPoll(w http.ResponseWriter, r *http.Request) {
	if s.oauthMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "oauth not available")
		return
	}
	state := r.URL.Query().Get("state")
	if state == "" {
		s.writeError(w, http.StatusBadRequest, "state is required")
		return
	}
	rec, granted, err := s.oauthMgr.PollDeviceCode(state)
	if err != nil {
		s.writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if !granted {
		s.writeJSON(w, http.StatusAccepted, map[string]any{"status": "pending"})
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{
		"connected": true,
		"provider":  "kiro",
		"expires_in": int(timeUntil(rec.ExpiresAt).Seconds()),
	})
}

func (s *Server) handleOAuthCallback(w http.ResponseWriter, r *http.Request) {
	if s.oauthMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "oauth not available")
		return
	}
	provider := chi.URLParam(r, "provider")
	code := r.URL.Query().Get("code")
	state := r.URL.Query().Get("state")
	if code == "" || state == "" {
		s.writeError(w, http.StatusBadRequest, "code and state are required")
		return
	}

	if provider != "antigravity" {
		s.writeError(w, http.StatusNotFound, "unknown provider")
		return
	}

	spec := oauth.PKCESpec{
		Name:         "antigravity",
		ClientID:     getEnvDefault("ANTIGRAVITY_CLIENT_ID", "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"),
		ClientSecret: getEnvDefault("ANTIGRAVITY_CLIENT_SECRET", ""),
		AuthorizeURL: "https://accounts.google.com/o/oauth2/v2/auth",
		TokenURL:     "https://oauth2.googleapis.com/token",
		RedirectURI:  "http://localhost:8000/dashboard/oauth/callback",
		Scopes:       nil,
	}
	if _, err := s.oauthMgr.CompletePKCE(state, code, spec); err != nil {
		s.writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	s.writeJSON(w, http.StatusOK, map[string]any{"provider": "antigravity", "connected": true})
}

func (s *Server) handleOAuthStatus(w http.ResponseWriter, r *http.Request) {
	if s.oauthMgr == nil {
		s.writeJSON(w, http.StatusOK, map[string]any{})
		return
	}
	s.writeJSON(w, http.StatusOK, s.oauthMgr.ConnectedProviders())
}

func (s *Server) handleOAuthDisconnect(w http.ResponseWriter, r *http.Request) {
	if s.oauthMgr == nil {
		s.writeError(w, http.StatusServiceUnavailable, "oauth not available")
		return
	}
	provider := chi.URLParam(r, "provider")
	if !s.oauthMgr.Delete(provider) {
		s.writeError(w, http.StatusNotFound, "provider not connected")
		return
	}
	s.writeJSON(w, http.StatusOK, map[string]any{"disconnected": provider})
}
