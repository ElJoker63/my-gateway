// Package security holds shared defense helpers: constant-time comparison,
// auth-failure rate limiting, and timing normalization.
package security

import (
	"crypto/sha256"
	"crypto/subtle"
	"sync"
	"time"
)

// EqualFold compares two strings in constant time. Safe for API keys.
func EqualFold(a, b string) bool {
	return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

// KeyHasher returns a stable hash of a key for comparison without
// exposing it to logs accidentally.
func KeyHash(key string) []byte {
	h := sha256.Sum256([]byte(key))
	return h[:]
}

// AuthLimiter throttles auth failures per source (IP/key fingerprint).
//
// Purpose: without this, a leaked partial key or a guessing endpoint lets an
// attacker brute-force the gateway key at full request rate.
type AuthLimiter struct {
	mu       sync.Mutex
	buckets  map[string]*bucket
	window   time.Duration
	max      int
}

type bucket struct {
	count     int
	windowAt  time.Time
}

// NewAuthLimiter returns a limiter allowing max attempts per window.
func NewAuthLimiter(max int, window time.Duration) *AuthLimiter {
	return &AuthLimiter{
		buckets: map[string]*bucket{},
		window:  window,
		max:     max,
	}
}

// Allow returns true if a request for key may proceed. Failures count toward
// the cap; successful calls reset the bucket.
func (a *AuthLimiter) Allow(key string) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	now := time.Now()
	b := a.buckets[key]
	if b == nil || now.Sub(b.windowAt) > a.window {
		b = &bucket{windowAt: now}
		a.buckets[key] = b
	}
	if b.count >= a.max {
		return false
	}
	b.count++
	return true
}

// Reset clears a bucket — call upon any successful auth.
func (a *AuthLimiter) Reset(key string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	delete(a.buckets, key)
}
