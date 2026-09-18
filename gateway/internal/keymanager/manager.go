// Package keymanager owns the per-provider API key pools.
//
// Semantics come from the gateway spec:
//   - Redis sliding-window per-key rate limiting, atomically claimed via Lua.
//   - Both "least_used" and "round_robin" strategies.
//   - Error cooldown per key after 429/401/403 from the upstream.
//   - Stable per-key fingerprint (sha-256 prefix) as the identity — masks are
//     only a UI convenience and can collide, so they're not identity.
package keymanager

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	keyPrefix       = "gw:keys"
	defaultWindowMs = 60_000
)

// Strategies accepted by Acquire.
const (
	StrategyLeastUsed  = "least_used"
	StrategyRoundRobin = "round_robin"
)

// KeyInfo describes one pool entry.
type KeyInfo struct {
	Key           string `json:"-"` // full key, never logged
	Fingerprint   string `json:"id"`
	Display       string `json:"display"`
	Index         int    `json:"index"`
	RequestsUsed  int    `json:"requests_used"`
	RequestsLimit int    `json:"requests_limit"`
}

// Pool is one provider's set of keys.
type Pool struct {
	Provider  string
	Keys      []*KeyInfo
	RPMPerKey int
	rrCursor  atomic.Uint32
	mu        sync.Mutex // guards Keys slice mutations
}

// ErrNoKeys is returned when a provider has no registered keys.
var ErrNoKeys = errors.New("no key pool registered for provider")

// ErrAllLimited is returned when every key is exhausted or in cooldown.
var ErrAllLimited = errors.New("all keys are in cooldown or rate-limited")

// Manager owns all pools plus the atomic acquire path over Redis.
type Manager struct {
	rdb      redis.UniversalClient
	strategy string
	waitFor  time.Duration

	mu    sync.RWMutex
	pools map[string]*Pool

	luaSha atomic.Value // string, loaded on first use
}

// New returns a Manager bound to the given Redis client.
func New(rdb redis.UniversalClient, strategy string, waitTimeoutSecs int) *Manager {
	if strategy == "" {
		strategy = StrategyLeastUsed
	}
	return &Manager{
		rdb:      rdb,
		strategy: strategy,
		waitFor:  time.Duration(waitTimeoutSecs) * time.Second,
		pools:    make(map[string]*Pool),
	}
}

// RegisterPool (re)registers a provider's keys.
func (m *Manager) RegisterPool(provider string, keys []string, rpmPerKey int) {
	if rpmPerKey <= 0 {
		rpmPerKey = 35
	}
	infos := make([]*KeyInfo, 0, len(keys))
	for i, k := range keys {
		infos = append(infos, &KeyInfo{
			Key:           k,
			Fingerprint:   fingerprint(k),
			Display:       maskKey(k),
			Index:         i,
			RequestsLimit: rpmPerKey,
		})
	}
	m.mu.Lock()
	m.pools[provider] = &Pool{Provider: provider, Keys: infos, RPMPerKey: rpmPerKey}
	m.mu.Unlock()
	slog.Info("key pool registered", "provider", provider, "keys", len(infos), "rpm_per_key", rpmPerKey)
}

// Redis exposes the underlying Redis client (used by other services to share
// a single connection).
func (m *Manager) Redis() redis.UniversalClient {
	return m.rdb
}

// AddKey appends a key to an existing pool (or creates one).
// Returns false if the key is already registered.
func (m *Manager) AddKey(provider, key string) bool {
	m.mu.RLock()
	pool, exists := m.pools[provider]
	m.mu.RUnlock()
	if !exists {
		m.RegisterPool(provider, []string{key}, 0)
		return true
	}

	fp := fingerprint(key)
	pool.mu.Lock()
	defer pool.mu.Unlock()
	for _, ki := range pool.Keys {
		if ki.Fingerprint == fp {
			return false
		}
	}
	pool.Keys = append(pool.Keys, &KeyInfo{
		Key:           key,
		Fingerprint:   fp,
		Display:       maskKey(key),
		Index:         len(pool.Keys),
		RequestsLimit: pool.RPMPerKey,
	})
	slog.Info("key added to pool", "provider", provider, "key", maskKey(key))
	return true
}

// HasPool reports whether a provider has keys registered.
func (m *Manager) HasPool(provider string) bool {
	pool := m.getPool(provider)
	return pool != nil && len(pool.Keys) > 0
}

// Pool returns the named pool (or nil).
func (m *Manager) Pool(provider string) *Pool {
	return m.getPool(provider)
}

// Providers returns all provider names with pools.
func (m *Manager) Providers() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]string, 0, len(m.pools))
	for name := range m.pools {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

func (m *Manager) getPool(provider string) *Pool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.pools[provider]
}

// keyStatus is one snapshot of a key's current state in Redis.
type keyStatus struct {
	key        *KeyInfo
	used       int
	limited    bool
	cooldown   bool
	retryAfter float64 // seconds until the sliding window frees a slot
}

// Acquire picks a key and atomically consumes one rate-limit slot.
//
// Snapshot → order claim attempts per strategy → for each candidate, one Lua
// call checks cooldown + window and consumes a slot atomically. A candidate
// that lost the race just falls through to the next.
func (m *Manager) Acquire(ctx context.Context, provider string) (*KeyInfo, error) {
	pool := m.getPool(provider)
	if pool == nil || len(pool.Keys) == 0 {
		return nil, fmt.Errorf("%w: %s", ErrNoKeys, provider)
	}

	deadline := time.Now().Add(m.waitFor)
	for {
		statuses := m.snapshotPool(ctx, pool)

		// Strategy-driven ordering
		ordered := m.order(statuses, pool)

		for _, st := range ordered {
			if st.cooldown || st.limited {
				continue
			}
			ok, err := m.claim(ctx, provider, st.key)
			if err != nil {
				// Redis failure — fail open, hand out the candidate.
				slog.Warn("claim failed, failing open", "provider", provider, "err", err)
				return cloneKey(st.key), nil
			}
			if ok {
				st.key.RequestsUsed = st.used + 1
				s := *st.key
				return &s, nil
			}
		}

		if time.Now().After(deadline) {
			return nil, fmt.Errorf("%w (provider %s)", ErrAllLimited, provider)
		}

		// Wait for the soonest freeing slot
		wait := 250 * time.Millisecond
		for _, st := range statuses {
			if st.cooldown {
				continue
			}
			if st.retryAfter > 0 {
				d := time.Duration(st.retryAfter*1000)*time.Millisecond + 50*time.Millisecond
				if d < wait {
					wait = d
				}
			}
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(wait):
		}
	}
}

// ReportError flags a key as having failed and sets its cooldown.
func (m *Manager) ReportError(ctx context.Context, provider, fingerprint, kind string, cooldownSecs int) {
	pool := m.getPool(provider)
	if pool == nil {
		return
	}
	if cooldownSecs <= 0 {
		cooldownSecs = 60
	}
	for _, ki := range pool.Keys {
		if ki.Fingerprint == fingerprint {
			errKey := fmt.Sprintf("%s:%s:%d:error", keyPrefix, provider, ki.Index)
			if err := m.rdb.Set(ctx, errKey, kind, time.Duration(cooldownSecs)*time.Second).Err(); err != nil {
				slog.Warn("cooldown persist failed", "provider", provider, "err", err)
			}
			slog.Warn("key entered cooldown", "provider", provider, "key", ki.Display, "kind", kind)
			return
		}
	}
}

// order returns candidates ranked per strategy.
func (m *Manager) order(statuses []keyStatus, pool *Pool) []keyStatus {
	out := make([]keyStatus, len(statuses))
	copy(out, statuses)
	switch m.strategy {
	case StrategyRoundRobin:
		if len(out) > 0 {
			shift := int(pool.rrCursor.Add(1) % uint32(len(out)))
			out = append(out[shift:], out[:shift]...)
		}
	default: // least_used
		sort.SliceStable(out, func(i, j int) bool { return out[i].used < out[j].used })
	}
	return out
}

// snapshotPool batch-reads all keys' rate/cooldown state in one pipeline.
func (m *Manager) snapshotPool(ctx context.Context, pool *Pool) []keyStatus {
	now := time.Now()
	windowStart := now.Add(-defaultWindowMs * time.Millisecond)

	pipe := m.rdb.Pipeline()
	type idx struct{ k *KeyInfo }
	counts := pipe.SCard // placeholder to use pipe; replaced below
	_ = counts

	var cmdZrem = make([]*redis.IntCmd, 0, len(pool.Keys))
	var cmdZcard = make([]*redis.IntCmd, 0, len(pool.Keys))
	var cmdExists = make([]*redis.IntCmd, 0, len(pool.Keys))
	var cmdZrange = make([]*redis.ZSliceCmd, 0, len(pool.Keys))

	for _, ki := range pool.Keys {
		rateKey := fmt.Sprintf("%s:%s:%d:requests", keyPrefix, pool.Provider, ki.Index)
		errKey := fmt.Sprintf("%s:%s:%d:error", keyPrefix, pool.Provider, ki.Index)
		cmdZrem = append(cmdZrem, pipe.ZRemRangeByScore(ctx, rateKey, "0", fmt.Sprint(windowStart.UnixMilli())))
		cmdZcard = append(cmdZcard, pipe.ZCard(ctx, rateKey))
		cmdExists = append(cmdExists, pipe.Exists(ctx, errKey))
		cmdZrange = append(cmdZrange, pipe.ZRangeWithScores(ctx, rateKey, 0, 0))
	}

	_, _ = pipe.Exec(ctx) // tolerate connection failure — callers handle nil counters

	out := make([]keyStatus, 0, len(pool.Keys))
	for i, ki := range pool.Keys {
		used := 0
		if cmdZcard[i] != nil && cmdZcard[i].Err() == nil {
			used = int(cmdZcard[i].Val())
		}
		inCd := false
		if cmdExists[i] != nil && cmdExists[i].Err() == nil {
			inCd = cmdExists[i].Val() > 0
		}
		retry := 0.0
		if cmdZrange[i] != nil && cmdZrange[i].Err() == nil {
			if zs := cmdZrange[i].Val(); len(zs) > 0 {
				if retryLast := float64(zs[0].Score) + float64(defaultWindowMs); retryLast > float64(now.UnixMilli()) {
					retry = (retryLast - float64(now.UnixMilli())) / 1000.0
				}
			}
		}
		limited := used >= ki.RequestsLimit
		out = append(out, keyStatus{
			key: ki, used: used, limited: limited, cooldown: inCd, retryAfter: retry,
		})
	}
	return out
}

// claim executes the atomic acquire Lua script once for one key.
func (m *Manager) claim(ctx context.Context, provider string, ki *KeyInfo) (bool, error) {
	rateKey := fmt.Sprintf("%s:%s:%d:requests", keyPrefix, provider, ki.Index)
	errKey := fmt.Sprintf("%s:%s:%d:error", keyPrefix, provider, ki.Index)
	nonce := fmt.Sprintf("%d-%s", time.Now().UnixNano(), ki.Fingerprint)

	const script = `
local exists = redis.call('EXISTS', KEYS[2])
if exists == 1 then return 0 end
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, tonumber(ARGV[1]) - tonumber(ARGV[2]))
local n = redis.call('ZCARD', KEYS[1])
if n >= tonumber(ARGV[3]) then return 2 end
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), tostring(ARGV[1]) .. '-' .. ARGV[4])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
`

	sha := m.shaOf(ctx, script)
	res, err := m.rdb.EvalSha(ctx, sha, []string{rateKey, errKey},
		time.Now().UnixMilli(), defaultWindowMs, ki.RequestsLimit, nonce).Int()
	if err != nil {
		if strings.Contains(err.Error(), "NOSCRIPT") {
			m.luaSha.Store("")
			res, err = m.rdb.EvalSha(ctx, m.shaOf(ctx, script), []string{rateKey, errKey},
				time.Now().UnixMilli(), defaultWindowMs, ki.RequestsLimit, nonce).Int()
			if err != nil {
				return false, err
			}
		} else {
			return false, err
		}
	}
	return res == 1, nil // 2 = rate-limited (slot not consumed), 0 = cooldown
}

// shaOf returns the SHA of the claim script, reloading on NOSCRIPT.
func (m *Manager) shaOf(ctx context.Context, script string) string {
	if v := m.luaSha.Load(); v != nil {
		if s, ok := v.(string); ok && s != "" {
			return s
		}
	}
	sha, err := m.rdb.ScriptLoad(ctx, script).Result()
	if err != nil {
		return ""
	}
	m.luaSha.Store(sha)
	return sha
}

// ------------------- helpers -------------------

func cloneKey(k *KeyInfo) *KeyInfo {
	if k == nil {
		return nil
	}
	out := *k
	return &out
}

func fingerprint(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])[:10]
}

func maskKey(key string) string {
	n := len(key)
	switch {
	case n <= 2:
		return "****"
	case n <= 8:
		return "****" + key[n-2:]
	default:
		return key[:3] + "****" + key[n-4:]
	}
}

// PersistReload merges runtime-added keys from Redis into the current pools.
func (m *Manager) PersistReload(ctx context.Context) {
	keys, err := m.rdb.Keys(ctx, "gw:provider_keys:*").Result()
	if err != nil || len(keys) == 0 {
		return
	}
	for _, full := range keys {
		provider := strings.TrimPrefix(full, "gw:provider_keys:")
		raw, err := m.rdb.HGet(ctx, full, "keys").Result()
		if err != nil {
			continue
		}
		var vals []string
		if err := json.Unmarshal([]byte(raw), &vals); err != nil || len(vals) == 0 {
			continue
		}
		pool := m.getPool(provider)
		if pool == nil {
			m.RegisterPool(provider, vals, 0)
			continue
		}
		// pool exists: only merge what's missing (by fingerprint).
		existing := map[string]bool{}
		for _, k := range pool.Keys {
			existing[k.Fingerprint] = true
		}
		for _, k := range vals {
			if !existing[fingerprint(k)] {
				m.AddKey(provider, k)
			}
		}
	}
}
