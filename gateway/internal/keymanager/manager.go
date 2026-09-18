// Package keymanager owns the per-provider API key pools.
// Now multi-tenant: pools live per (tenant, provider). The "system" tenant holds
// the env-provided keys; each gateway user has their own tenant keyed by id.
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

// TenantID for the shared system pool (env-provided keys).
const TenantSystem = "system"

// Strategies accepted by Acquire.
const (
	StrategyLeastUsed  = "least_used"
	StrategyRoundRobin = "round_robin"
)

// KeyInfo describes one pool entry.
type KeyInfo struct {
	Key           string `json:"-"`
	Fingerprint   string `json:"id"`
	Display       string `json:"display"`
	Index         int    `json:"index"`
	RequestsUsed  int    `json:"requests_used"`
	RequestsLimit int    `json:"requests_limit"`
}

// Pool is one provider's set of keys (for one tenant).
type Pool struct {
	Provider  string
	Keys      []*KeyInfo
	RPMPerKey int
	rrCursor  atomic.Uint32
	mu        sync.Mutex
}

// Errors.
var (
	ErrNoKeys     = errors.New("no key pool registered for provider")
	ErrAllLimited = errors.New("all keys are in cooldown or rate-limited")
)

// Manager owns all pools plus the atomic acquire path over Redis.
type Manager struct {
	rdb      redis.UniversalClient
	strategy string
	waitFor  time.Duration

	mu    sync.RWMutex                        // guards pools map
	pools map[string]map[string]*Pool        // [tenant][provider] → pool

	luaSha atomic.Value
}

// New returns a Manager bound to Redis.
func New(rdb redis.UniversalClient, strategy string, waitTimeoutSecs int) *Manager {
	if strategy == "" {
		strategy = StrategyLeastUsed
	}
	return &Manager{
		rdb:      rdb,
		strategy: strategy,
		waitFor:  time.Duration(waitTimeoutSecs) * time.Second,
		pools:    map[string]map[string]*Pool{},
	}
}

// Redis exposes the underlying client.
func (m *Manager) Redis() redis.UniversalClient { return m.rdb }

// HasPool reports whether (tenant, provider) has keys.
func (m *Manager) HasPool(tenant, provider string) bool {
	return m.getPool(tenant, provider) != nil
}

// Pool returns the pool for (tenant, provider), or nil.
func (m *Manager) Pool(tenant, provider string) *Pool {
	return m.getPool(tenant, provider)
}

// Providers lists every distinct provider name across all tenants.
func (m *Manager) Providers() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	seen := map[string]bool{}
	for _, byProvider := range m.pools {
		for name := range byProvider {
			seen[name] = true
		}
	}
	out := make([]string, 0, len(seen))
	for name := range seen {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

// Tenants lists every tenant seen so far.
func (m *Manager) Tenants() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := make([]string, 0, len(m.pools))
	for t := range m.pools {
		out = append(out, t)
	}
	return out
}

func (m *Manager) getPool(tenant, provider string) *Pool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if byProvider, ok := m.pools[tenant]; ok {
		return byProvider[provider]
	}
	return nil
}

// RegisterPool (re)registers (tenant, provider)'s keys.
func (m *Manager) RegisterPool(tenant, provider string, keys []string, rpmPerKey int) {
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
	if m.pools[tenant] == nil {
		m.pools[tenant] = map[string]*Pool{}
	}
	m.pools[tenant][provider] = &Pool{Provider: provider, Keys: infos, RPMPerKey: rpmPerKey}
	m.mu.Unlock()
	slog.Info("key pool registered", "tenant", tenant, "provider", provider, "keys", len(infos))
}

// AddKey appends a key.
func (m *Manager) AddKey(tenant, provider, key string) bool {
	m.mu.RLock()
	pool, exists := m.pools[tenant]
	m.mu.RUnlock()
	if !exists {
		m.RegisterPool(tenant, provider, []string{key}, 0)
		return true
	}
	p := pool[provider]
	if p == nil {
		m.RegisterPool(tenant, provider, []string{key}, 0)
		return true
	}
	fp := fingerprint(key)
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, ki := range p.Keys {
		if ki.Fingerprint == fp {
			return false
		}
	}
	p.Keys = append(p.Keys, &KeyInfo{
		Key:           key,
		Fingerprint:   fp,
		Display:       maskKey(key),
		Index:         len(p.Keys),
		RequestsLimit: p.RPMPerKey,
	})
	return true
}

// keyStatus is one snapshot of a key's current state.
type keyStatus struct {
	key        *KeyInfo
	used       int
	limited    bool
	cooldown   bool
	retryAfter float64
}

// Acquire picks a key for (tenant, provider).
func (m *Manager) Acquire(ctx context.Context, tenant, provider string) (*KeyInfo, error) {
	pool := m.getPool(tenant, provider)
	if pool == nil || len(pool.Keys) == 0 {
		return nil, fmt.Errorf("%w (tenant=%s provider=%s)", ErrNoKeys, tenant, provider)
	}

	deadline := time.Now().Add(m.waitFor)
	for {
		statuses := m.snapshotPool(ctx, pool, tenant)
		ordered := m.order(statuses, pool)

		for _, st := range ordered {
			if st.cooldown || st.limited {
				continue
			}
			ok, err := m.claim(ctx, tenant, provider, st.key)
			if err != nil {
				slog.Warn("claim failed, failing open", "provider", provider, "err", err)
				return cloneKey(st.key), nil
			}
			if ok {
				st.key.RequestsUsed = st.used + 1
				return cloneKey(st.key), nil
			}
		}

		if time.Now().After(deadline) {
			return nil, fmt.Errorf("%w (provider %s)", ErrAllLimited, provider)
		}

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

// ReportError flags a key as failed.
func (m *Manager) ReportError(ctx context.Context, tenant, provider, fingerprint, kind string, cooldownSecs int) {
	pool := m.getPool(tenant, provider)
	if pool == nil {
		return
	}
	if cooldownSecs <= 0 {
		cooldownSecs = 60
	}
	for _, ki := range pool.Keys {
		if ki.Fingerprint == fingerprint {
			errKey := fmt.Sprintf("%s:%s:%s:%d:error", keyPrefix, tenant, provider, ki.Index)
			if err := m.rdb.Set(ctx, errKey, kind, time.Duration(cooldownSecs)*time.Second).Err(); err != nil {
				slog.Warn("cooldown persist failed", "provider", provider, "err", err)
			}
			slog.Warn("key entered cooldown", "provider", provider, "key", ki.Display)
			return
		}
	}
}

// order orders candidates per strategy.
func (m *Manager) order(statuses []keyStatus, pool *Pool) []keyStatus {
	out := make([]keyStatus, len(statuses))
	copy(out, statuses)
	switch m.strategy {
	case StrategyRoundRobin:
		if len(out) > 0 {
			shift := int(pool.rrCursor.Add(1) % uint32(len(out)))
			out = append(out[shift:], out[:shift]...)
		}
	default:
		sort.SliceStable(out, func(i, j int) bool { return out[i].used < out[j].used })
	}
	return out
}

// snapshotPool batch-reads all keys of pool.
func (m *Manager) snapshotPool(ctx context.Context, pool *Pool, tenant string) []keyStatus {
	if len(pool.Keys) == 0 {
		return nil
	}
	now := time.Now()
	windowStart := now.Add(-defaultWindowMs * time.Millisecond)

	pipe := m.rdb.Pipeline()
	cmdZcard := make([]*redis.IntCmd, 0, len(pool.Keys))
	cmdExists := make([]*redis.IntCmd, 0, len(pool.Keys))
	cmdZrange := make([]*redis.ZSliceCmd, 0, len(pool.Keys))
	cmdZrem := make([]*redis.IntCmd, 0, len(pool.Keys))

	for _, ki := range pool.Keys {
		rateKey := fmt.Sprintf("%s:%s:%s:%d:requests", keyPrefix, tenant, pool.Provider, ki.Index)
		errKey := fmt.Sprintf("%s:%s:%s:%d:error", keyPrefix, tenant, pool.Provider, ki.Index)
		cmdZrem = append(cmdZrem, pipe.ZRemRangeByScore(ctx, rateKey, "0", fmt.Sprint(windowStart.UnixMilli())))
		cmdZcard = append(cmdZcard, pipe.ZCard(ctx, rateKey))
		cmdExists = append(cmdExists, pipe.Exists(ctx, errKey))
		cmdZrange = append(cmdZrange, pipe.ZRangeWithScores(ctx, rateKey, 0, 0))
	}
	_, _ = pipe.Exec(ctx)

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
				retryAfter := float64(zs[0].Score) + float64(defaultWindowMs) - float64(now.UnixMilli())
				if retryAfter < 0 {
					retryAfter = 0
				}
				retry = retryAfter / 1000.0
			}
		}
		out = append(out, keyStatus{
			key: ki, used: used, limited: used >= ki.RequestsLimit, cooldown: inCd, retryAfter: retry,
		})
		_ = cmdZrem[i]
	}
	return out
}

// claim executes the atomic Lua acquire script once per candidate key.
func (m *Manager) claim(ctx context.Context, tenant, provider string, ki *KeyInfo) (bool, error) {
	rateKey := fmt.Sprintf("%s:%s:%s:%d:requests", keyPrefix, tenant, provider, ki.Index)
	errKey := fmt.Sprintf("%s:%s:%s:%d:error", keyPrefix, tenant, provider, ki.Index)
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
			sha = m.shaOf(ctx, script)
			res, err = m.rdb.EvalSha(ctx, sha, []string{rateKey, errKey},
				time.Now().UnixMilli(), defaultWindowMs, ki.RequestsLimit, nonce).Int()
			if err != nil {
				return false, err
			}
		} else {
			return false, err
		}
	}
	return res == 1, nil
}

// shaOf returns the sha of the claim script, reloading after NOSCRIPT.
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

// PersistReload merges runtime-added keys that Redis already knows about.
func (m *Manager) PersistReload(ctx context.Context, tenant string) {
	if m.rdb == nil {
		return
	}
	keys, err := m.rdb.Keys(ctx, "gw:provider_keys:"+tenant+":*").Result()
	if err != nil || len(keys) == 0 {
		return
	}
	for _, full := range keys {
		provider := strings.TrimPrefix(full, "gw:provider_keys:"+tenant+":")
		raw, err := m.rdb.HGet(ctx, full, "keys").Result()
		if err != nil {
			continue
		}
		var vals []string
		if err := json.Unmarshal([]byte(raw), &vals); err != nil || len(vals) == 0 {
			continue
		}
		pool := m.getPool(tenant, provider)
		if pool == nil {
			m.RegisterPool(tenant, provider, vals, 0)
			continue
		}
		existing := map[string]bool{}
		for _, k := range pool.Keys {
			existing[k.Fingerprint] = true
		}
		for _, k := range vals {
			if !existing[fingerprint(k)] {
				m.AddKey(tenant, provider, k)
			}
		}
	}
}

func fingerprint(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])[:10]
}

func cloneKey(k *KeyInfo) *KeyInfo {
	if k == nil {
		return nil
	}
	out := *k
	return &out
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
