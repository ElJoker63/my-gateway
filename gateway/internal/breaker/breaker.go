// Package breaker is a per-(provider|provider:model) circuit breaker.
//
// After `Threshold` consecutive failures the target goes "open" and is
// skipped for `OpenFor` seconds. After the window it half-opens: one probe is
// allowed through; success closes it, failure reopens it. State is kept in
// process — Redis would just be a shared side store here, and the whole point
// of a breaker is that it's cheap to consult.
package breaker

import (
	"sync"
	"time"
)

// State values.
const (
	StateClosed   = "closed"
	StateOpen     = "open"
	StateHalfOpen = "half_open"
)

type entry struct {
	failures int
	until    time.Time
	state    string
}

// Breaker tracks one provider's circuit state.
type Breaker struct {
	mu        sync.Mutex
	threshold int
	openFor   time.Duration
	states    map[string]*entry
}

// New builds a Breaker. threshold <= 0 defaults to 3; openForSecs <= 0 defaults to 60.
func New(threshold, openForSecs int) *Breaker {
	if threshold <= 0 {
		threshold = 3
	}
	if openForSecs <= 0 {
		openForSecs = 60
	}
	return &Breaker{
		threshold: threshold,
		openFor:   time.Duration(openForSecs) * time.Second,
		states:    make(map[string]*entry),
	}
}

// Available reports whether the target can accept traffic right now.
func (b *Breaker) Available(provider string, model string) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	e, ok := b.states[key(provider, model)]
	if !ok {
		return true
	}
	if e.state == StateOpen && time.Now().After(e.until) {
		e.state = StateHalfOpen // allow the probe through
		return true
	}
	return e.state != StateOpen
}

// Success clears the failure counter, closing the circuit.
func (b *Breaker) Success(provider string, model string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	delete(b.states, key(provider, model))
}

// Failure registers one failed call. After `threshold` consecutive failures
// the circuit opens for `openFor`.
func (b *Breaker) Failure(provider string, model string) string {
	b.mu.Lock()
	defer b.mu.Unlock()
	k := key(provider, model)
	e := b.states[k]
	if e == nil {
		e = &entry{state: StateClosed}
		b.states[k] = e
	}
	e.failures++
	if e.failures >= b.threshold && e.state != StateOpen {
		e.state = StateOpen
		e.until = time.Now().Add(b.openFor)
	}
	return e.state
}

// Snapshot returns the current state per key (for /api/metrics).
func (b *Breaker) Snapshot() map[string]map[string]any {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := make(map[string]map[string]any, len(b.states))
	now := time.Now()
	for k, e := range b.states {
		state := e.state
		if state == StateOpen && now.After(e.until) {
			state = StateHalfOpen
		}
		out[k] = map[string]any{
			"state":    state,
			"failures": e.failures,
		}
	}
	return out
}

func key(provider, model string) string {
	if model == "" {
		return provider
	}
	return provider + ":" + model
}
