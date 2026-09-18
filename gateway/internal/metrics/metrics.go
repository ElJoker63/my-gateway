// Package metrics is the in-process telemetry store.
//
// Latency percentiles are computed over a small rolling window per
// (provider, model) bucket. The global counters sit behind a mutex since
// requests can come from many goroutines.
package metrics

import (
	"sort"
	"sync"
	"time"
)

// Window is how many samples we keep per (provider, model) for percentiles.
const Window = 512

type providerStats struct {
	Requests int
	Errors   int
	Tokens   int
	Models   map[string]struct{}
}

type sample struct {
	at    time.Time
	ms    float64
	tokens int
}

// Store is the global metrics registry.
type Store struct {
	mu           sync.RWMutex
	total        int
	errors       int
	races        int
	raceWins     int
	startedAt    time.Time
	perProvider  map[string]*providerStats
	latency      map[string][]sample // key = provider:model
}

// New returns an empty Store.
func New() *Store {
	return &Store{
		startedAt:   time.Now(),
		perProvider: map[string]*providerStats{},
		latency:     map[string][]sample{},
	}
}

var (
	// global is the singleton — services register to it directly.
	global = New()
)

// Global returns the singleton registry.
func Global() *Store {
	return global
}

// Record registers one upstream call outcome.
func (s *Store) Record(provider, model string, latencyMs float64, ok bool, tokens int, raced, won bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.total++
	if !ok {
		s.errors++
	}
	if raced {
		s.races++
	}
	if won {
		s.raceWins++
	}

	p := s.perProvider[provider]
	if p == nil {
		p = &providerStats{Models: map[string]struct{}{}}
		s.perProvider[provider] = p
	}
	p.Requests++
	if !ok {
		p.Errors++
	}
	p.Tokens += tokens
	if model != "" {
		p.Models[model] = struct{}{}
	}

	key := provider + ":" + model
	buf := s.latency[key]
	if buf == nil {
		buf = make([]sample, 0, Window)
	}
	buf = append(buf, sample{at: time.Now(), ms: latencyMs, tokens: tokens})
	if len(buf) > Window {
		buf = buf[len(buf)-Window:]
	}
	s.latency[key] = buf
}

// Summary renders the registry for /api/metrics.
func (s *Store) Summary() map[string]any {
	s.mu.RLock()
	defer s.mu.RUnlock()

	providers := map[string]any{}
	for name, p := range s.perProvider {
		models := make([]string, 0, len(p.Models))
		for m := range p.Models {
			models = append(models, m)
		}
		sort.Strings(models)
		errRate := 0.0
		if p.Requests > 0 {
			errRate = float64(p.Errors) / float64(p.Requests)
		}
		providers[name] = map[string]any{
			"requests":    p.Requests,
			"errors":      p.Errors,
			"error_rate":  round4(errRate),
			"tokens":      p.Tokens,
			"models":      models,
		}
	}

	latency := map[string]any{}
	for key, buf := range s.latency {
		if len(buf) == 0 {
			continue
		}
		sorted := make([]float64, len(buf))
		for i, s := range buf {
			sorted[i] = s.ms
		}
		sort.Float64s(sorted)
		sum := 0.0
		for _, v := range sorted {
			sum += v
		}
		latency[key] = map[string]any{
			"count":  len(buf),
			"p50_ms": round2(percentile(sorted, 50)),
			"p95_ms": round2(percentile(sorted, 95)),
			"p99_ms": round2(percentile(sorted, 99)),
			"avg_ms": round2(sum / float64(len(buf))),
		}
	}

	errorRate := 0.0
	if s.total > 0 {
		errorRate = float64(s.errors) / float64(s.total)
	}
	winRate := 0.0
	if s.races > 0 {
		winRate = float64(s.raceWins) / float64(s.races)
	}

	return map[string]any{
		"uptime_seconds":   time.Since(s.startedAt).Seconds(),
		"total_requests":   s.total,
		"total_errors":     s.errors,
		"error_rate":       round4(errorRate),
		"total_races":      s.races,
		"race_wins":        s.raceWins,
		"race_win_rate":    round4(winRate),
		"providers":        providers,
		"latency":          latency,
	}
}

func percentile(sorted []float64, p float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	k := float64(len(sorted)-1) * (p / 100.0)
	lo := int(k)
	hi := lo + 1
	if hi >= len(sorted) {
		hi = len(sorted) - 1
	}
	frac := k - float64(lo)
	return sorted[lo] + (sorted[hi]-sorted[lo])*frac
}

func round2(f float64) float64 { return roundN(f, 2) }
func round4(f float64) float64 { return roundN(f, 4) }

func roundN(f float64, places int) float64 {
	mul := 1.0
	for i := 0; i < places; i++ {
		mul *= 10
	}
	return float64(int(f*mul+0.5)) / mul
}
