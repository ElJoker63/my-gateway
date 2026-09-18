// Package cache is the Redis-backed response cache.
//
// Key derivation is param-aware: two requests differing only in e.g.
// temperature never share a cached answer. Project invalidation relies on a
// per-project set index (gw:cache:project:{name}).
package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

const (
	cachePrefix    = "gw:cache:"
	projectIndexPfx = "gw:cache:project:"
	statsKey        = "gw:cache:stats"
)

// Store is the public cache interface.
type Store struct {
	rdb redis.UniversalClient
	ttl time.Duration
}

// New builds a cache bound to the given Redis client.
func New(rdb redis.UniversalClient, ttlSecs int) *Store {
	if ttlSecs <= 0 {
		ttlSecs = 86400
	}
	return &Store{rdb: rdb, ttl: time.Duration(ttlSecs) * time.Second}
}

// paramFields is the whitelist of params that participate in the cache key.
var paramFields = []string{
	"temperature", "top_p", "max_tokens", "stop",
	"frequency_penalty", "presence_penalty", "n",
	"tools", "tool_choice", "response_format",
}

// Key builds a deterministic cache key for one request.
func Key(messages any, model, project string, params map[string]any) string {
	effective := map[string]any{}
	for _, k := range paramFields {
		if v, ok := params[k]; ok && v != nil {
			effective[k] = v
		}
	}
	blob := map[string]any{
		"messages": messages,
		"model":    model,
		"project":  project,
		"params":   effective,
	}
	buf, _ := json.Marshal(blob)
	sum := sha256.Sum256(buf)
	return cachePrefix + hex.EncodeToString(sum[:])
}

// Get retrieves a cached response. Hits bump the stats counter.
func (s *Store) Get(ctx context.Context, key string) (map[string]any, bool) {
	raw, err := s.rdb.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		s.incr(ctx, "misses")
		return nil, false
	}
	if err != nil {
		slog.Warn("cache read failed", "err", err)
		return nil, false
	}
	s.incr(ctx, "hits")
	out := map[string]any{}
	if err := json.Unmarshal([]byte(raw), &out); err != nil {
		return nil, false
	}
	return out, true
}

// Set stores a response; also appends the key to the project's index set.
func (s *Store) Set(ctx context.Context, key string, response map[string]any, project string) {
	buf, err := json.Marshal(response)
	if err != nil {
		return
	}
	pipe := s.rdb.TxPipeline()
	pipe.Set(ctx, key, buf, s.ttl)
	idxKey := projectIndexPfx + project
	pipe.SAdd(ctx, idxKey, key)
	pipe.Expire(ctx, idxKey, s.ttl)
	if _, err := pipe.Exec(ctx); err != nil {
		slog.Warn("cache write failed", "err", err)
	}
}

// InvalidateProject drops every cached entry for a project.
func (s *Store) InvalidateProject(ctx context.Context, project string) int {
	idxKey := projectIndexPfx + project
	keys, err := s.rdb.SMembers(ctx, idxKey).Result()
	if err != nil || len(keys) == 0 {
		_ = s.rdb.Del(ctx, idxKey).Err()
		return 0
	}
	n := 0
	if keys != nil {
		dn, err := s.rdb.Del(ctx, keys...).Result()
		if err == nil {
			n = int(dn)
		}
	}
	s.rdb.Del(ctx, idxKey)
	return n
}

// Stats returns the hit/miss counters.
func (s *Store) Stats(ctx context.Context) map[string]int {
	out := map[string]int{"hits": 0, "misses": 0}
	vals, err := s.rdb.HGetAll(ctx, statsKey).Result()
	if err != nil {
		return out
	}
	if h, ok := vals["hits"]; ok {
		if n, e := strconv.Atoi(h); e == nil {
			out["hits"] = n
		}
	}
	if m, ok := vals["misses"]; ok {
		if n, e := strconv.Atoi(m); e == nil {
			out["misses"] = n
		}
	}
	return out
}

func (s *Store) incr(ctx context.Context, field string) {
	if err := s.rdb.HIncrBy(ctx, statsKey, field, 1).Err(); err != nil {
		slog.Debug("stats incr failed", "err", err)
	}
}
