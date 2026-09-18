// Package combos is the model-alias registry.
//
// A combo is a named list of targets (provider + optional model) plus a
// routing strategy. Requests use model="combo:<name>" to route through it.
// Fresh Persp: stored in Redis with an in-memory mirror.
package combos

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

// Strategy names.
const (
	StrategyStrict     = "strict"
	StrategyRoundRobin = "round_robin"
	StrategyLeastUsed  = "least_used"
	StrategyRace       = "race"
)

// Target names one provider (+optional model override) in a combo.
type Target struct {
	Provider string `json:"provider"`
	Model    string `json:"model,omitempty"`
	Weight   int    `json:"weight,omitempty"`
}

// Combo is the user-facing named chain.
type Combo struct {
	Name      string    `json:"name"`
	Targets   []Target  `json:"targets"`
	Strategy  string    `json:"strategy"`
	RaceSize  int       `json:"race_size"`
	CreatedAt time.Time `json:"created_at"`
}

// Store keeps combos in Redis ("gw:combo:*") with a local read-through mirror.
type Store struct {
	rdb   redis.UniversalClient
	local map[string]*Combo
	mu    sync.RWMutex
}

// New returns an empty Store bound to Redis.
func New(rdb redis.UniversalClient) *Store {
	return &Store{rdb: rdb, local: map[string]*Combo{}}
}

const (
	comboPrefix = "gw:combo:"
	comboIndex  = "gw:combos:index"
)

// Save upserts a combo.
func (s *Store) Save(ctx context.Context, c *Combo) error {
	if c.Name == "" {
		return errInvalid("name is required")
	}
	if len(c.Targets) == 0 {
		return errInvalid("at least one target is required")
	}
	if c.Strategy == "" {
		c.Strategy = StrategyStrict
	}
	if c.RaceSize < 2 {
		c.RaceSize = 2
	}
	if c.CreatedAt.IsZero() {
		c.CreatedAt = time.Now()
	}
	s.mu.Lock()
	s.local[c.Name] = c
	s.mu.Unlock()
	if s.rdb == nil {
		return nil
	}
	buf, err := json.Marshal(c)
	if err != nil {
		return err
	}
	pipe := s.rdb.TxPipeline()
	pipe.Set(ctx, comboPrefix+c.Name, buf, 0)
	pipe.SAdd(ctx, comboIndex, c.Name)
	if _, err := pipe.Exec(ctx); err != nil {
		slog.Warn("combo persist to Redis failed", "name", c.Name, "err", err)
	}
	return nil
}

// Get returns a combo by name (with or without the "combo:" prefix).
func (s *Store) Get(ctx context.Context, name string) (*Combo, bool) {
	name = strings.TrimPrefix(name, "combo:")

	s.mu.RLock()
	if c, ok := s.local[name]; ok {
		s.mu.RUnlock()
		return c, true
	}
	s.mu.RUnlock()
	if s.rdb == nil {
		return nil, false
	}

	raw, err := s.rdb.Get(ctx, comboPrefix+name).Result()
	if err != nil {
		return nil, false
	}
	var c Combo
	if err := json.Unmarshal([]byte(raw), &c); err != nil {
		return nil, false
	}
	s.mu.Lock()
	s.local[name] = &c
	s.mu.Unlock()
	return &c, true
}

// List returns every registered combo.
func (s *Store) List(ctx context.Context) []*Combo {
	if s.rdb == nil {
		s.mu.RLock()
		defer s.mu.RUnlock()
		out := make([]*Combo, 0, len(s.local))
		for _, c := range s.local {
			out = append(out, c)
		}
		return out
	}
	names, err := s.rdb.SMembers(ctx, comboIndex).Result()
	out := []*Combo{}
	if err == nil {
		for _, n := range names {
			raw, err := s.rdb.Get(ctx, comboPrefix+n).Result()
			if err != nil {
				continue
			}
			var c Combo
			if json.Unmarshal([]byte(raw), &c) == nil {
				out = append(out, &c)
			}
		}
		return out
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, c := range s.local {
		out = append(out, c)
	}
	return out
}

// Delete removes a combo.
func (s *Store) Delete(ctx context.Context, name string) bool {
	name = strings.TrimPrefix(name, "combo:")
	if s.rdb != nil {
		pipe := s.rdb.TxPipeline()
		pipe.Del(ctx, comboPrefix+name)
		pipe.SRem(ctx, comboIndex, name)
		_, _ = pipe.Exec(ctx)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	_, existed := s.local[name]
	delete(s.local, name)
	return existed
}

func errInvalid(msg string) error { return &invalidComboError{msg: msg} }

type invalidComboError struct{ msg string }

func (e *invalidComboError) Error() string { return e.msg }
