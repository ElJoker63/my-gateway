// Package oauth implements the OAuth handshake engines: PKCE (Google) and
// AWS SSO OIDC device code (Kiro).
//
// Tokens persist under gw:oauth:{provider} in Redis. The local cache is purely
// a read-through mirror.
package oauth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

// TokenRecord is the persisted OAuth session.
type TokenRecord struct {
	AccessToken  string         `json:"access_token"`
	RefreshToken string         `json:"refresh_token,omitempty"`
	ExpiresAt    time.Time      `json:"expires_at"`
	Scopes       []string       `json:"scopes"`
	Meta         map[string]any `json:"meta,omitempty"`
}

// PendingFlow holds the state for an in-flight handshake.
type PendingFlow struct {
	Provider   string
	State      string
	Verifier   string // PKCE verifier (also used as client_id:secret for device flow)
	DeviceCode string
	CreatedAt  time.Time
}

// Manager owns flows plus the persisted token store.
type Manager struct {
	rdb       redis.UniversalClient
	http      *http.Client

	mu      sync.Mutex
	pending map[string]*PendingFlow

	local map[string]*TokenRecord // memory mirror of Redis
}

// New returns a manager.
func New(rdb redis.UniversalClient) *Manager {
	return &Manager{
		rdb:     rdb,
		http:    &http.Client{Timeout: 30 * time.Second},
		pending: map[string]*PendingFlow{},
		local:   map[string]*TokenRecord{},
	}
}

// ------------------------- PKCE (Google) -------------------------

var pkceAlphabet = []rune("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

func randomString(n int) string {
	buf := make([]byte, n)
	_, _ = rand.Read(buf)
	out := make([]rune, n)
	for i, b := range buf {
		out[i] = pkceAlphabet[int(b)%len(pkceAlphabet)]
	}
	return string(out)
}

// sha256Sum is sha256(data).
func sha256Sum(b []byte) [32]byte { return sha256.Sum256(b) }

// base64URLEncode is base64-url without padding (RFC 4648 §5).
func base64URLEncode(b []byte) string {
	return base64.RawURLEncoding.EncodeToString(b)
}

type PKCESpec struct {
	Name          string
	ClientID      string
	ClientSecret  string
	AuthorizeURL  string
	TokenURL      string
	RedirectURI   string
	Scopes        []string
}

// StartPKCE builds an authorization URL and stores the pending verifier.
func (m *Manager) StartPKCE(spec PKCESpec) (string, string, error) {
	verifier := randomString(64)
	sum := sha256Sum([]byte(verifier))
	challenge := base64URLEncode(sum[:])

	state := randomString(24)
	m.mu.Lock()
	m.pending[state] = &PendingFlow{
		Provider: spec.Name,
		State:    state,
		Verifier: verifier,
		CreatedAt: time.Now(),
	}
	m.mu.Unlock()

	q := url.Values{}
	q.Set("client_id", spec.ClientID)
	q.Set("redirect_uri", spec.RedirectURI)
	q.Set("response_type", "code")
	q.Set("scope", strings.Join(spec.Scopes, " "))
	q.Set("code_challenge", challenge)
	q.Set("code_challenge_method", "S256")
	q.Set("access_type", "offline")
	q.Set("prompt", "consent")
	q.Set("state", state)

	return spec.AuthorizeURL + "?" + q.Encode(), state, nil
}

// CompletePKCE exchanges a callback code for tokens and stores them.
func (m *Manager) CompletePKCE(state, code string, spec PKCESpec) (*TokenRecord, error) {
	m.mu.Lock()
	flow, ok := m.pending[state]
	m.mu.Unlock()
	if !ok {
		return nil, errors.New("unknown or expired OAuth state")
	}

	form := url.Values{}
	form.Set("grant_type", "authorization_code")
	form.Set("code", code)
	form.Set("client_id", spec.ClientID)
	form.Set("client_secret", spec.ClientSecret)
	form.Set("redirect_uri", spec.RedirectURI)
	form.Set("code_verifier", flow.Verifier)

	req, err := http.NewRequest(http.MethodPost, spec.TokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := m.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return nil, fmt.Errorf("token exchange failed: %d %s", resp.StatusCode, string(body))
	}
	var tr map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&tr); err != nil {
		return nil, err
	}

	rec := parseTokenResponse(tr)
	if rec.AccessToken == "" {
		return nil, errors.New("token response missing access_token")
	}
	m.mu.Lock()
	delete(m.pending, state)
	m.mu.Unlock()

	if err := m.save(context.Background(), spec.Name, rec); err != nil {
		return nil, err
	}
	return rec, nil
}

// ------------------------- Device code (AWS OIDC) -------------------------

type DeviceCodeSpec struct {
	Provider        string
	OIDCBase        string // https://oidc.us-east-1.amazonaws.com
	Scopes          []string
}

// StartDeviceCode registers a transient OIDC client and starts a device flow.
func (m *Manager) StartDeviceCode(spec DeviceCodeSpec) (map[string]any, error) {
	registerBody := map[string]any{
		"clientName": "my-gateway-" + spec.Provider,
		"clientType": "public",
		"scopes":     spec.Scopes,
		"grantTypes": []string{
			"urn:ietf:params:oauth:grant-type:device_code",
			"refresh_token",
		},
	}
	reg, err := m.postJSON(spec.OIDCBase+"/client/register", registerBody)
	if err != nil {
		return nil, err
	}
	clientID, _ := reg["clientId"].(string)
	clientSecret, _ := reg["clientSecret"].(string)
	if clientID == "" || clientSecret == "" {
		return nil, errors.New("OIDC registration missing clientId/clientSecret")
	}

	dev, err := m.postJSON(spec.OIDCBase+"/device_authorization", map[string]any{
		"clientId":     clientID,
		"clientSecret": clientSecret,
		"startUrl":     "https://device.sso.us-east-1.amazonaws.com/",
	})
	if err != nil {
		return nil, err
	}

	deviceCode, _ := dev["deviceCode"].(string)
	userCode, _ := dev["userCode"].(string)
	verificationURI, _ := dev["verificationUri"].(string)
	verificationURIComplete, _ := dev["verificationUriComplete"].(string)
	expiresIn, _ := dev["expiresIn"].(float64)
	interval, _ := dev["interval"].(float64)
	if interval <= 0 {
		interval = 5
	}

	state := randomString(24)
	m.mu.Lock()
	m.pending[state] = &PendingFlow{
		Provider:   spec.Provider,
		State:      state,
		Verifier:   clientID + ":" + clientSecret,
		DeviceCode: deviceCode,
		CreatedAt:  time.Now(),
	}
	m.mu.Unlock()

	return map[string]any{
		"provider":                 spec.Provider,
		"flow":                     "device_code",
		"verificationUri":          verificationURI,
		"verificationUriComplete":  verificationURIComplete,
		"userCode":                 userCode,
		"expiresIn":                int(expiresIn),
		"interval":                 int(interval),
		"state":                    state,
	}, nil
}

// PollDeviceCode checks one device-code flow; 202 while pending, error later.
func (m *Manager) PollDeviceCode(state string) (*TokenRecord, bool, error) {
	m.mu.Lock()
	flow, ok := m.pending[state]
	m.mu.Unlock()
	if !ok {
		return nil, false, errors.New("unknown OAuth state")
	}

	parts := strings.SplitN(flow.Verifier, ":", 2)
	if len(parts) != 2 {
		return nil, false, errors.New("malformed client credentials")
	}

	tokenBody := map[string]any{
		"clientId":     parts[0],
		"clientSecret": parts[1],
		"deviceCode":   flow.DeviceCode,
		"grantType":    "urn:ietf:params:oauth:grant-type:device_code",
	}
	tr, err := m.postJSON("https://oidc.us-east-1.amazonaws.com/token", tokenBody)
	if err != nil {
		// AWS returns 400 with `authorization_pending` while waiting
		msg := err.Error()
		if strings.Contains(msg, "authorization_pending") || strings.Contains(msg, "slow_down") {
			return nil, false, nil
		}
		return nil, false, err
	}

	rec := parseTokenResponse(tr)
	if rec.AccessToken == "" {
		return nil, false, errors.New("token response missing access token")
	}

	m.mu.Lock()
	delete(m.pending, state)
	m.mu.Unlock()

	if err := m.save(context.Background(), flow.Provider, rec); err != nil {
		return nil, false, err
	}
	return rec, true, nil
}

// ------------------------- Token storage -------------------------

func (m *Manager) key(provider string) string { return "gw:oauth:" + provider }

// Save persists a token.
func (m *Manager) save(ctx context.Context, provider string, rec *TokenRecord) error {
	buf, err := json.Marshal(rec)
	if err != nil {
		return err
	}
	if err := m.rdb.Set(ctx, m.key(provider), buf, 0).Err(); err != nil {
		return err
	}
	m.mu.Lock()
	m.local[provider] = rec
	m.mu.Unlock()
	return nil
}

// Get returns the stored record, or nil.
func (m *Manager) Get(provider string) *TokenRecord {
	m.mu.Lock()
	if rec, ok := m.local[provider]; ok {
		m.mu.Unlock()
		return rec
	}
	m.mu.Unlock()

	raw, err := m.rdb.Get(context.Background(), m.key(provider)).Result()
	if err != nil {
		return nil
	}
	var rec TokenRecord
	if json.Unmarshal([]byte(raw), &rec) != nil {
		return nil
	}
	m.mu.Lock()
	m.local[provider] = &rec
	m.mu.Unlock()
	return &rec
}

// AccessToken returns the current access token; refreshes if near expiry.
func (m *Manager) AccessToken(provider string) string {
	rec := m.Get(provider)
	if rec == nil {
		return ""
	}
	if time.Until(rec.ExpiresAt) < 60*time.Second && rec.RefreshToken != "" {
		if refreshed, err := m.refresh(provider, rec); err == nil {
			rec = refreshed
		}
	}
	return rec.AccessToken
}

// ProjectID returns a provider-specific extra (e.g. antigravity's cloud project).
func (m *Manager) ProjectID(provider string) string {
	rec := m.Get(provider)
	if rec == nil || rec.Meta == nil {
		return ""
	}
	if v, ok := rec.Meta["project_id"].(string); ok {
		return v
	}
	return ""
}

// ConnectedProviders lists providers with live tokens.
func (m *Manager) ConnectedProviders() map[string]map[string]any {
	out := map[string]map[string]any{}
	m.mu.Lock()
	defer m.mu.Unlock()
	for name, rec := range m.local {
		out[name] = map[string]any{
			"connected":   time.Now().Before(rec.ExpiresAt),
			"expires_in":  int(time.Until(rec.ExpiresAt).Seconds()),
		}
	}
	// Merge any tokens that are only in Redis (multi-worker restart)
	if keys, err := m.rdb.Keys(context.Background(), "gw:oauth:*").Result(); err == nil {
		for _, key := range keys {
			name := strings.TrimPrefix(key, "gw:oauth:")
			if _, seen := out[name]; seen {
				continue
			}
			if rec := m.Get(name); rec != nil {
				out[name] = map[string]any{
					"connected":  time.Now().Before(rec.ExpiresAt),
					"expires_in": int(time.Until(rec.ExpiresAt).Seconds()),
				}
			}
		}
	}
	return out
}

// Delete removes a provider's token.
func (m *Manager) Delete(provider string) bool {
	m.mu.Lock()
	delete(m.local, provider)
	m.mu.Unlock()
	n, _ := m.rdb.Del(context.Background(), m.key(provider)).Result()
	return n > 0
}

func (m *Manager) refresh(provider string, rec *TokenRecord) (*TokenRecord, error) {
	// Generic refresh — calls the same token endpoint with refresh_token grant.
	// The caller knows the right token URL; for our two providers they're both
	// in the spec. To stay simple we store the token URL in the record's Meta.
	tokenURL, _ := rec.Meta["token_url"].(string)
	if tokenURL == "" {
		return nil, errors.New("no token URL stored for refresh")
	}
	form := url.Values{}
	form.Set("grant_type", "refresh_token")
	form.Set("refresh_token", rec.RefreshToken)
	form.Set("client_id", fmt.Sprint(rec.Meta["client_id"]))

	req, err := http.NewRequest(http.MethodPost, tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	resp, err := m.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("refresh failed: %d", resp.StatusCode)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	fresh := parseTokenResponse(out)
	if fresh.RefreshToken == "" {
		fresh.RefreshToken = rec.RefreshToken
	}
	if err := m.save(context.Background(), provider, fresh); err != nil {
		return nil, err
	}
	return fresh, nil
}

func parseTokenResponse(m map[string]any) *TokenRecord {
	access, _ := m["access_token"].(string)
	if access == "" {
		access, _ = m["accessToken"].(string)
	}
	rec := &TokenRecord{
		AccessToken:  access,
		RefreshToken: firstStr(m, "refresh_token", "refreshToken"),
		Scopes:       splitScopes(firstStr(m, "scope", "scopes")),
		Meta:         map[string]any{},
	}
	if v, ok := m["expires_in"].(float64); ok {
		rec.ExpiresAt = time.Now().Add(time.Duration(v) * time.Second)
	} else if v := m["expiresIn"]; v != nil {
		if f, ok := v.(float64); ok {
			rec.ExpiresAt = time.Now().Add(time.Duration(f) * time.Second)
		}
	}
	if rec.RefreshToken == "" {
		rec.RefreshToken = firstStr(m, "refreshToken", "refresh_token")
	}
	return rec
}

func firstStr(m map[string]any, keys ...string) string {
	for _, k := range keys {
		if v, ok := m[k].(string); ok && v != "" {
			return v
		}
	}
	return ""
}

func splitScopes(v string) []string {
	if v == "" {
		return nil
	}
	return strings.Fields(v)
}

func (m *Manager) postJSON(url string, body any) (map[string]any, error) {
	buf, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequest(http.MethodPost, url, io.NopCloser(bytesReader(buf)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := m.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(raw))
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// bytesReader wraps []byte into io.Reader without extra imports.
func bytesReader(b []byte) io.Reader { return strings.NewReader(string(b)) }
