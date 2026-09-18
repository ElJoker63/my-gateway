package combos

import (
	"context"
	"testing"
)

func testCtx() context.Context { return context.Background() }


func TestSaveGetDelete(t *testing.T) {
	s := New(nil) // nil redis — exercises the local-fallback path
	c := &Combo{
		Name: "fast",
		Targets:   []Target{{Provider: "nvidia"}, {Provider: "groq", Model: "llama"}},
		Strategy:  StrategyRace,
		RaceSize:  2,
	}
	if err := s.Save(testCtx(), c); err != nil {
		t.Fatal(err)
	}

	got, ok := s.Get(testCtx(), "fast")
	if !ok || got.Name != "fast" || got.Strategy != StrategyRace {
		t.Fatalf("Get failed: %v %v", ok, got)
	}

	got2, ok2 := s.Get(testCtx(), "combo:fast")
	if !ok2 || got2.Name != "fast" {
		t.Fatal("prefixed lookup should work")
	}

	if s.Delete(testCtx(), "fast") != true {
		t.Fatal("Delete should report existed")
	}
	if _, ok := s.Get(testCtx(), "fast"); ok {
		t.Fatal("combo should be gone")
	}
}

func TestList(t *testing.T) {
	s := New(nil)
	s.Save(testCtx(), &Combo{Name: "a", Targets: []Target{{Provider: "nvidia"}}})
	s.Save(testCtx(), &Combo{Name: "b", Targets: []Target{{Provider: "groq"}}})
	list := s.List(testCtx())
	if len(list) != 2 {
		t.Fatalf("want 2, got %d", len(list))
	}
}

func TestValidation(t *testing.T) {
	s := New(nil)
	if err := s.Save(testCtx(), &Combo{}); err == nil {
		t.Fatal("empty name should fail")
	}
	if err := s.Save(testCtx(), &Combo{Name: "x"}); err == nil {
		t.Fatal("no targets should fail")
	}
}
