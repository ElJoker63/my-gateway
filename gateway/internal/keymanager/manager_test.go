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

	if !km.AddKey(TenantSystem, "nvidia", "nv-test-key-1") {
		t.Fatal("first AddKey should succeed")
	}
	if km.AddKey(TenantSystem, "nvidia", "nv-test-key-1") {
		t.Fatal("duplicate AddKey should fail")
	}
	if !km.AddKey(TenantSystem, "nvidia", "nv-test-key-2") {
		t.Fatal("new key should be accepted")
	}

	pool := km.Pool(TenantSystem, "nvidia")
	if pool == nil || len(pool.Keys) != 2 {
		t.Fatalf("pool should have 2 keys, got %v", pool)
	}
	if pool.Keys[0].Fingerprint == pool.Keys[1].Fingerprint {
		t.Fatal("fingerprints should differ")
	}
}

// TestPoolIsolation tenants do not share keys.
func TestPoolIsolation(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: ":0"})
	km := New(rdb, StrategyLeastUsed, 5)

	km.AddKey("alice", "nvidia", "alice-key")
	km.AddKey("bob", "nvidia", "bob-key")

	if km.Pool("alice", "nvidia").Keys[0].Key == km.Pool("bob", "nvidia").Keys[0].Key {
		t.Fatal("tenants should hold separate keys")
	}
	if km.Pool("", "nvidia") != nil {
		t.Fatal("system tenant should not see user pools")
	}
}

// TestRegisterPoolDefaultRPM covers the default rpm behavior.
func TestRegisterPoolDefaultRPM(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: ":0"})
	km := New(rdb, StrategyLeastUsed, 5)
	km.RegisterPool(TenantSystem, "groq", []string{"k1"}, 0)

	pool := km.Pool(TenantSystem, "groq")
	if pool.RPMPerKey != 35 {
		t.Fatalf("default RPM should be 35, got %d", pool.RPMPerKey)
	}
}

// Smoke coverage.
func TestHasPoolAndProviders(t *testing.T) {
	rdb := redis.NewClient(&redis.Options{Addr: ":0"})
	km := New(rdb, StrategyLeastUsed, 5)
	if km.HasPool(TenantSystem, "nothing") {
		t.Fatal("no pool registered initially")
	}
	km.RegisterPool(TenantSystem, "nvidia", []string{"k"}, 0)
	if !km.HasPool(TenantSystem, "nvidia") {
		t.Fatal("pool should be registered")
	}
	if len(km.Providers()) == 0 {
		t.Fatal("providers map should not be empty")
	}
}

var _ = context.Background
