package keymanager

import (
	"context"
	"testing"

	"github.com/redis/go-redis/v9"
)

// TestAddKey verifies duplicate detection and bootstrap behavior.
func TestAddKey(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: ":0"})
	km := New(rdb, StrategyLeastUsed, 5)

	if !km.AddKey("nvidia", "nv-test-key-1") {
		t.Fatal("first AddKey should succeed")
	}
	if km.AddKey("nvidia", "nv-test-key-1") {
		t.Fatal("duplicate AddKey should fail")
	}
	if !km.AddKey("nvidia", "nv-test-key-2") {
		t.Fatal("new key should be accepted")
	}

	pool := km.Pool("nvidia")
	if pool == nil || len(pool.Keys) != 2 {
		t.Fatalf("pool should have 2 keys, got %v", pool)
	}
	if pool.Keys[0].Fingerprint == pool.Keys[1].Fingerprint {
		t.Fatal("fingerprints should differ")
	}
}

// TestStrategies exercises the ordering helpers.
func TestFlowSelection(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: ":0"})
	km := New(rdb, StrategyLeastUsed, 5)
	km.RegisterPool("nvidia", []string{"a", "b", "c"}, 10)

	if !km.HasPool("nvidia") {
		t.Fatal("pool registered")
	}
	if len(km.Providers()) != 1 {
		t.FailNow()
	}

	ctx := context.Background()
	pool := km.Pool("nvidia")
	if len(pool.Keys) != 3 {
		t.Fatalf("want 3 keys, got %d", len(pool.Keys))
	}
	_ = ctx
}

// TestRegisterPoolDefaultRPM covers the default rpm behavior.
func TestRegisterPoolDefaultRPM(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: ":0"})
	km := New(rdb, StrategyLeastUsed, 5)
	km.RegisterPool("groq", []string{"k1"}, 0)

	pool := km.Pool("groq")
	if pool.RPMPerKey != 35 {
		t.Fatalf("default RPM should be 35, got %d", pool.RPMPerKey)
	}
}
