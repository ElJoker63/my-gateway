package breaker

import (
	"testing"
	"time"
)

func TestBreakerTransitions(t *testing.T) {
	b := New(3, 1) // threshold 3, 1s window

	if !b.Available("nvidia", "") {
		t.Fatal("should start closed/available")
	}

	// two failures → still available
	b.Failure("nvidia", "")
	b.Failure("nvidia", "")
	if !b.Available("nvidia", "") {
		t.Fatal("should still be available before threshold")
	}

	// third failure → open
	b.Failure("nvidia", "")
	if b.Available("nvidia", "") {
		t.Fatal("circuit should open after threshold")
	}

	// after window, half-open probe allowed
	time.Sleep(1100 * time.Millisecond)
	if !b.Available("nvidia", "") {
		t.Fatal("should be half-open after window expires")
	}
}

func TestSuccessResets(t *testing.T) {
	b := New(2, 10)
	b.Failure("nvidia", "")
	b.Failure("nvidia", "")
	if b.Available("nvidia", "") {
		t.Fatal("circuit should open")
	}
	b.Success("nvidia", "")
	if !b.Available("nvidia", "") {
		t.Fatal("success should close the circuit")
	}
}

func TestPerModelScope(t *testing.T) {
	b := New(1, 5)
	b.Failure("nvidia", "m1")
	if b.Available("nvidia", "m1") {
		t.Fatal("m1 should be unavailable")
	}
	if !b.Available("nvidia", "m2") {
		t.Fatal("m2 should still be available")
	}
	if !b.Available("nvidia", "") {
		t.Fatal("provider-level should still be available when only m1 tripped")
	}
}
