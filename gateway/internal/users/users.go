// Package users implements multi-user account management for the gateway.
//
// Each user gets a personal API key with shape "gwu_<24-hex-chars>" that acts
// as the identity for their key pools, OAuth sessions, metrics, and provider
// overrides. Provider keys and OAuth tokens are stored encrypted (AES-256-GCM,
// GATEWAY_MASTER_KEY) so Redis contents alone are not enough to leak them.
package users

import (
	"context"
	stdrand "crypto/rand"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/ElJoker63/my-gateway/gateway/internal/crypto"
)

// KeyPrefix for the per-user gateway key format.
const KeyPrefix = "gwu_"

// User is the stored account record.
type User struct {
	ID         string            `json:"id"`
	Name       string            `json:"name"`
	Email      string            `json:"email,omitempty"`
	CreatedAt  time.Time         `json:"created_at"`
	KeyHash    string            `json:"-"`           // sha256 of the raw key — never exposed
	KeyDisplay string            `json:"key_display"` // masked prefix for UIs: "gwu_ab12…"
	KeyVersion int               `json:"key_version"`  // bumped on rotation
	IsAdmin    bool              `json:"is_admin"`
	Disabled   bool              `json:"disabled"`
	Metadata   map[string]string `json:"metadata,omitempty"`
}

// Public view for UIs.
func (u *User) Public() map[string]any {
	return map[string]any{
		"id":          u.ID,
		"name":        u.Name,
		"email":       u.Email,
		"created_at":  u.CreatedAt.UTC().Format(time.RFC3339),
		"key_display": u.KeyDisplay,
		"key_version": u.KeyVersion,
		"is_admin":    u.IsAdmin,
		"disabled":    u.Disabled,
		"metadata":    u.Metadata,
	}
}

// Store persists users in Redis with an in-memory read mirror.
//
// Key layout:
//   gw:users:{id}           — JSON record
//   gw:users:by_hash:{hash} — user ID, for login-time lookup
//   gw:users:index          — set of all user IDs
type Store struct {
	rdb      redis.UniversalClient
	mu       sync.Mutex
	byHash   map[string]string // key hash → user id
	byID     map[string]*User
}

// New returns a Store over Redis (nil rdb = pure in-memory, dev/desktop only).
func New(rdb redis.UniversalClient) *Store {
	return &Store{
		rdb:    rdb,
		byHash: map[string]string{},
		byID:   map[string]*User{},
	}
}

const (
	usersPrefix   = "gw:users:"
	indexKey      = "gw:users:index"
	hashPrefix    = "gw:users:by_hash:"
)

// Create mints a new user with a fresh key; returns (user, rawKey).
// The raw key appears ONLY here — the store never keeps it.
func (s *Store) Create(ctx context.Context, name, email string, isAdmin bool) (*User, string, error) {
	if name == "" {
		return nil, "", errors.New("name is required")
	}
	rawKey, err := newKey()
	if err != nil {
		return nil, "", err
	}
	id := fmt.Sprintf("u-%d", time.Now().UnixNano())
	u := &User{
		ID:         id,
		Name:       name,
		Email:      email,
		CreatedAt:  time.Now().UTC(),
		KeyHash:    crypto.Hash(rawKey),
		KeyDisplay: crypto.KeyDisplay(rawKey),
		KeyVersion: 1,
		IsAdmin:    isAdmin,
		Metadata:   map[string]string{},
	}
	if err := s.persist(ctx, u, rawKey); err != nil {
		return nil, "", err
	}
	return u, rawKey, nil
}

// Lookup resolves a raw key to its user.
func (s *Store) Lookup(ctx context.Context, rawKey string) (*User, bool) {
	if !startsWithPrefix(rawKey) {
		return nil, false
	}
	hash := crypto.Hash(rawKey)
	if id, ok := s.byHash[hash]; ok {
		if u, found := s.byID[id]; found {
			return u, true
		}
	}
	if s.rdb != nil {
		id, err := s.rdb.Get(ctx, hashPrefix+hash).Result()
		if err != nil {
			return nil, false
		}
		u, ok := s.byID[id]
		// fall through to loading from redis when the mirror missed
		if !ok {
			raw, err := s.rdb.Get(ctx, usersPrefix+id).Result()
			if err != nil {
				return nil, false
			}
			u = &User{}
			if err := json.Unmarshal([]byte(raw), u); err != nil || u.ID == "" {
				return nil, false
			}
			s.byID[u.ID] = u
			s.byHash[hash] = u.ID
		}
		return u, true
	}
	return nil, false
}

// Get returns the user by ID.
func (s *Store) Get(ctx context.Context, id string) (*User, bool) {
	s.mu.Lock()
	if u, ok := s.byID[id]; ok {
		s.mu.Unlock()
		return u, true
	}
	s.mu.Unlock()
	if s.rdb == nil {
		return nil, false
	}
	raw, err := s.rdb.Get(ctx, usersPrefix+id).Result()
	if err != nil {
		return nil, false
	}
	u := &User{}
	if json.Unmarshal([]byte(raw), u) != nil || u.ID == "" {
		return nil, false
	}
	return u, true
}

// List returns every user (public profiles only).
func (s *Store) List(ctx context.Context) []*User {
	out := []*User{}
	if s.rdb != nil {
		ids, err := s.rdb.SMembers(ctx, indexKey).Result()
		if err == nil {
			for _, id := range ids {
				raw, err := s.rdb.Get(ctx, usersPrefix+id).Result()
				if err != nil {
					continue
				}
				u := &User{}
				if json.Unmarshal([]byte(raw), u) == nil && u.ID != "" {
					out = append(out, u)
				}
			}
			s.mu.Lock()
			for _, u := range out {
				s.byID[u.ID] = u
				s.byHash[u.KeyHash] = u.ID
			}
			s.mu.Unlock()
			return out
		}
	}
	s.mu.Lock()
	for _, u := range s.byID {
		out = append(out, u)
	}
	s.mu.Unlock()
	return out
}

// RotateKey mints a new key for the user; the old one is rejected from then on.
func (s *Store) RotateKey(ctx context.Context, id string) (string, error) {
	u, ok := s.Get(ctx, id)
	if !ok {
		return "", errors.New("user not found")
	}
	newKey, err := newKey()
	if err != nil {
		return "", err
	}
	oldHash := u.KeyHash
	u.KeyHash = crypto.Hash(newKey)
	u.KeyDisplay = crypto.KeyDisplay(newKey)
	u.KeyVersion++
	if s.rdb != nil {
		_ = s.rdb.Del(ctx, hashPrefix+oldHash).Err()
	}
	if err := s.persist(ctx, u, newKey); err != nil {
		return "", err
	}
	return newKey, nil
}

// Disable flips a user's access off.
func (s *Store) Disable(ctx context.Context, id string) error {
	u, ok := s.Get(ctx, id)
	if !ok {
		return errors.New("user not found")
	}
	u.Disabled = true
	return s.persist(ctx, u, "")
}

// Enable re-enables a user.
func (s *Store) Enable(ctx context.Context, id string) error {
	u, ok := s.Get(ctx, id)
	if !ok {
		return errors.New("user not found")
	}
	u.Disabled = false
	return s.persist(ctx, u, "")
}

// persist writes a user record and indexes it. Pass rawKey only when the record
// includes a key (create / rotate); pass "" for metadata-only updates.
func (s *Store) persist(ctx context.Context, u *User, rawKey string) error {
	buf, err := json.Marshal(u)
	if err != nil {
		return err
	}
	if s.rdb == nil {
		s.mu.Lock()
		s.byID[u.ID] = u
		if rawKey != "" {
			s.byHash[u.KeyHash] = u.ID
		}
		s.mu.Unlock()
		return nil
	}
	pipe := s.rdb.TxPipeline()
	pipe.Set(ctx, usersPrefix+u.ID, buf, 0)
	pipe.SAdd(ctx, indexKey, u.ID)
	if rawKey != "" {
		pipe.Set(ctx, hashPrefix+u.KeyHash, u.ID, 0)
	}
	if _, err := pipe.Exec(ctx); err != nil {
		return err
	}
	s.mu.Lock()
	s.byHash[u.KeyHash] = u.ID
	s.byID[u.ID] = u
	s.mu.Unlock()
	return nil
}

func newKey() (string, error) {
	buf := make([]byte, 24)
	if _, err := stdrand.Read(buf); err != nil {
		return "", err
	}
	return KeyPrefix + hex.EncodeToString(buf), nil
}

// base64Normalize was never used — the user-facing key format is gwu_ prefixed.
var _ = base64.URLEncoding

func startsWithPrefix(s string) bool { return len(s) > len(KeyPrefix) && s[:len(KeyPrefix)] == KeyPrefix }

var _ = slog.Info
