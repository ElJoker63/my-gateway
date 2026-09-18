// My Gateway AI — Go gateway server entrypoint.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ElJoker63/my-gateway/gateway/internal/api"
	"github.com/ElJoker63/my-gateway/gateway/internal/breaker"
	"github.com/ElJoker63/my-gateway/gateway/internal/cache"
	"github.com/ElJoker63/my-gateway/gateway/internal/combos"
	"github.com/ElJoker63/my-gateway/gateway/internal/config"
	"github.com/ElJoker63/my-gateway/gateway/internal/keymanager"
	"github.com/ElJoker63/my-gateway/gateway/internal/memory"
	"github.com/ElJoker63/my-gateway/gateway/internal/metrics"
	"github.com/ElJoker63/my-gateway/gateway/internal/oauth"
	"github.com/ElJoker63/my-gateway/gateway/internal/providers"

	"github.com/redis/go-redis/v9"
)

func main() {
	// Logging — structured, level from env
	level := slog.LevelInfo
	switch os.Getenv("LOG_LEVEL") {
	case "DEBUG":
		level = slog.LevelDebug
	case "WARN", "WARNING":
		level = slog.LevelWarn
	case "ERROR":
		level = slog.LevelError
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level})))

	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return fmt.Errorf("config: %w", err)
	}
	if err := cfg.Validate(); err != nil {
		return fmt.Errorf("config invalid: %w", err)
	}

	// Redis — required for key pools, combos, cache, OAuth tokens
	rdb := redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", cfg.RedisHost, cfg.RedisPort),
		Password: cfg.RedisPassword,
	})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		slog.Error("redis ping failed", "err", err)
		return fmt.Errorf("redis not reachable at %s:%d", cfg.RedisHost, cfg.RedisPort)
	}
	slog.Info("redis connected", "host", cfg.RedisHost, "port", cfg.RedisPort)

	// Qdrant (vector memory — optional if the backend is down)
	mem := memory.New(cfg.QdrantHost, cfg.QdrantPort, cfg.QdrantKey, cfg.EmbeddingDimension)
	if ok := mem.Health(context.Background()); ok {
		slog.Info("qdrant connected", "host", cfg.QdrantHost, "port", cfg.QdrantPort)
	} else {
		slog.Warn("qdrant not reachable — memory endpoints will be degraded")
	}

	// Services
	keys := keymanager.New(rdb, cfg.DefaultProvider, cfg.RateLimitWaitSecs)
	for _, name := range config.ProviderNames() {
		keys.RegisterPool(name, cfg.KeysFor(name), cfg.RPMFor(name))
	}
	// Reload keys added at runtime via the API
	keys.PersistReload(context.Background())

	br := breaker.New(cfg.CircuitFailureThreshold, cfg.CircuitUnhealthySecs)
	cacheStore := cache.New(rdb, cfg.CacheTTLSecs)
	comboStore := combos.New(rdb)
	oauthMgr := oauth.New(rdb)
	metrics.Global() // initialize the registry singleton

	// Bridge: OAuth tokens that providers need at request time
	providers.SetOAuthHooks(
		func(provider string) string { return oauthMgr.AccessToken(provider) },
		func(provider string) string { return oauthMgr.ProjectID(provider) },
	)

	// HTTP server
	srv, err := api.NewServer(cfg)
	if err != nil {
		return err
	}
	srv.AttachInfra(keys, cacheStore, comboStore, oauthMgr, mem, br)

	httpServer := &http.Server{
		Addr:         fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		Handler:      srv,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 300 * time.Second,
		IdleTimeout:  90 * time.Second,
	}

	slog.Info("My Gateway AI listening", "addr", httpServer.Addr)
	slog.Info("dashboard", "url", fmt.Sprintf("http://%s:%d/dashboard/", cfg.Host, cfg.Port))

	// Shutdown handler
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)

	errCh := make(chan error, 1)
	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
		}
	}()

	select {
	case err := <-errCh:
		return err
	case s := <-sig:
		slog.Info("shutdown signal received", "signal", s)
		ctxShutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := httpServer.Shutdown(ctxShutdown); err != nil {
			slog.Error("shutdown failed", "err", err)
			return err
		}
		slog.Info("gateway stopped cleanly")
		return nil
	}
}
