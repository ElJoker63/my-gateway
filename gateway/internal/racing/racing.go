// Package racing implements the routing strategies over combo targets.
//
// race = launch N targets concurrently, first valid result wins, losers are
// cancelled; strict/round_robin/least_used fall through in order.
package racing

import (
	"context"
	"errors"
	"sort"
	"sync"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/combos"
	"github.com/ElJoker63/my-gateway/gateway/internal/keymanager"
)

// ErrAllTargetsFailed fires when every target errored.
var ErrAllTargetsFailed = errors.New("all combo targets failed")

// Result is a single attempt's outcome.
type Result struct {
	Target   combos.Target
	Response any
	UsedKey  string
}

// AttemptFunc is the caller-provided per-target execution body.
type AttemptFunc func(ctx context.Context, target combos.Target) (any, error)

// Options control race/failover behavior.
type Options struct {
	AttemptTimeout time.Duration
	Parallelism    int
	// Tenant selects whose key pools to use for ordering / fallbacks.
	// Empty string = system pool (env-provided keys).
	Tenant string
}

// Execute runs a combo under its strategy.
func Execute(ctx context.Context, combo *combos.Combo, km *keymanager.Manager, attempt AttemptFunc, opts Options) (*Result, error) {
	targets := orderTargets(combo, km, opts.Tenant)
	if len(targets) == 0 {
		return nil, errors.New("combo has no targets")
	}
	if opts.AttemptTimeout <= 0 {
		opts.AttemptTimeout = 90 * time.Second
	}
	if opts.Parallelism <= 0 {
		opts.Parallelism = combo.RaceSize
	}

	if combo.Strategy == combos.StrategyRace && len(targets) > 1 {
		return race(ctx, targets, attempt, opts)
	}
	return failover(ctx, targets, attempt, opts)
}

func race(ctx context.Context, targets []combos.Target, attempt AttemptFunc, opts Options) (*Result, error) {
	take := opts.Parallelism
	if take > len(targets) {
		take = len(targets)
	}
	group := targets[:take]

	type outcome struct {
		target combos.Target
		resp   any
		err    error
	}
	results := make(chan outcome, take)

	ctxAll, cancelAll := context.WithCancel(ctx)
	defer cancelAll()

	var wg sync.WaitGroup
	for _, t := range group {
		wg.Add(1)
		go func(t combos.Target) {
			defer wg.Done()
			ctxAttempt, cancel := context.WithTimeout(ctxAll, opts.AttemptTimeout)
			defer cancel()
			resp, err := attempt(ctxAttempt, t)
			if err == nil {
				results <- outcome{target: t, resp: resp}
				return
			}
			results <- outcome{target: t, err: err}
		}(t)
	}

	go func() { wg.Wait(); close(results) }()

	var lastErr error
	for {
		select {
		case oc, ok := <-results:
			if !ok {
				if lastErr != nil {
					return nil, lastErr
				}
				return nil, ErrAllTargetsFailed
			}
			if oc.err == nil {
				cancelAll()
				return &Result{Target: oc.target, Response: oc.resp}, nil
			}
			lastErr = oc.err
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
}

func failover(ctx context.Context, targets []combos.Target, attempt AttemptFunc, opts Options) (*Result, error) {
	var lastErr error
	for _, t := range targets {
		ctxAttempt, cancel := context.WithTimeout(ctx, opts.AttemptTimeout)
		resp, err := attempt(ctxAttempt, t)
		cancel()
		if err == nil {
			return &Result{Target: t, Response: resp}, nil
		}
		lastErr = err
	}
	if lastErr == nil {
		lastErr = ErrAllTargetsFailed
	}
	return nil, lastErr
}

// orderTargets orders a combo's targets per strategy.
func orderTargets(combo *combos.Combo, km *keymanager.Manager, tenant string) []combos.Target {
	out := make([]combos.Target, len(combo.Targets))
	copy(out, combo.Targets)

	switch combo.Strategy {
	case combos.StrategyLeastUsed:
		sortLeastUsed(out, km, tenant)
	}
	return out
}

// sortLeastUsed orders targets ascending by current pool usage.
func sortLeastUsed(targets []combos.Target, km *keymanager.Manager, tenant string) {
	if km == nil {
		return
	}
	usage := make(map[string]int, len(targets))
	for _, t := range targets {
		if pool := km.Pool(tenant, t.Provider); pool != nil {
			sum := 0
			for _, k := range pool.Keys {
				sum += k.RequestsUsed
			}
			usage[t.Provider] = sum
		}
	}
	sort.SliceStable(targets, func(i, j int) bool {
		return usage[targets[i].Provider] < usage[targets[j].Provider]
	})
}
