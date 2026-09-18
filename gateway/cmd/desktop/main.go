// Desktop shell: runs the My Gateway AI inside a Wails window.
//
// The Go gateway runs in-process on the default port; the webview loads the
// built SPA from app/dashboard/dist. All API calls go through the same server.
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

	"github.com/wailsapp/wails/v2"
	"github.com/wailsapp/wails/v2/pkg/options"
	"github.com/wailsapp/wails/v2/pkg/options/assetserver"

	"github.com/ElJoker63/my-gateway/gateway/internal/api"
	"github.com/ElJoker63/my-gateway/gateway/internal/breaker"
	"github.com/ElJoker63/my-gateway/gateway/internal/cache"
	"github.com/ElJoker63/my-gateway/gateway/internal/combos"
	"github.com/ElJoker63/my-gateway/gateway/internal/config"
	"github.com/ElJoker63/my-gateway/gateway/internal/keymanager"
	"github.com/ElJoker63/my-gateway/gateway/internal/memory"
	"github.com/ElJoker63/my-gateway/gateway/internal/oauth"
	"github.com/ElJoker63/my-gateway/gateway/internal/providers"
	"github.com/ElJoker63/my-gateway/gateway/internal/users"

	"github.com/redis/go-redis/v9"
)

// App is the Wails binding surface (methods exposed to JavaScript).
type App struct {
	ctx     context.Context
	server  *http.Server
	started chan struct{}
}

// NewApp builds the desktop shell.
func NewApp() *App { return &App{started: make(chan struct{})} }

func (a *App) OnStartup(ctx context.Context) {
	a.ctx = ctx
	go func() {
		if err := a.startGateway(); err != nil {
			slog.Error("gateway failed", "err", err)
		}
	}()
}

func (a *App) OnDomReady(ctx context.Context) {}

func (a *App) OnShutdown(ctx context.Context) {
	if a.server != nil {
		ctxDone, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = a.server.Shutdown(ctxDone)
	}
}

// startGateway boots the Go gateway in-process on the configured port.
func (a *App) startGateway() error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}

	rdb := redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", cfg.RedisHost, cfg.RedisPort),
		Password: cfg.RedisPassword,
	})
	if err := rdb.Ping(context.Background()).Err(); err != nil {
		return fmt.Errorf("redis not reachable: %w", err)
	}

	keys := keymanager.New(rdb, cfg.DefaultProvider, cfg.RateLimitWaitSecs)
	for _, name := range config.ProviderNames() {
		keys.RegisterPool(keymanager.TenantSystem, name, cfg.KeysFor(name), cfg.RPMFor(name))
	}
	keys.PersistReload(context.Background(), keymanager.TenantSystem)

	mem := memory.New(cfg.QdrantHost, cfg.QdrantPort, cfg.QdrantKey, cfg.EmbeddingDimension)
	br := breaker.New(cfg.CircuitFailureThreshold, cfg.CircuitUnhealthySecs)
	cacheStore := cache.New(rdb, cfg.CacheTTLSecs)
	comboStore := combos.New(rdb)
	oauthMgr := oauth.New(rdb)

	providers.SetOAuthHooks(
		func(p string) string { return oauthMgr.AccessToken(p) },
		func(p string) string { return oauthMgr.ProjectID(p) },
	)

	srv, err := api.NewServer(cfg)
	if err != nil {
		return err
	}
	srv.AttachInfra(keys, cacheStore, comboStore, oauthMgr, mem, br, users.New(rdb))

	a.server = &http.Server{
		Addr:    fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		Handler: srv,
	}
	slog.Info("gateway up (embedded in desktop shell)", "addr", a.server.Addr)
	return a.server.ListenAndServe()
}

func runDesktop() error {
	// Ensure the backend works before opening the window
	go func() {
		// Wait for the gateway to accept requests before showing the UI.
		for {
			resp, err := http.Get(fmt.Sprintf("http://localhost:%d/health", 8000))
			if err == nil && resp.StatusCode == 200 && resp.Body != nil {
				resp.Body.Close()
				break
			}
			time.Sleep(80 * time.Millisecond)
		}
	}()

	app := NewApp()
	err := wails.Run(&options.App{
		Title:     "My Gateway AI",
		Width:     1280,
		Height:    900,
		MinWidth:  960,
		MinHeight: 640,
		AssetServer: &assetserver.Options{
			Assets: os.DirFS(dashDistDir()),
		},
		BackgroundColour: &options.RGBA{R: 10, G: 10, B: 12, A: 255},
		OnStartup:        app.OnStartup,
		OnDomReady:       app.OnDomReady,
		OnShutdown:       app.OnShutdown,
		Bind:             []interface{}{app},
	})
	return err
}

// dashDistDir locates the built SPA — the Wails binary expects it next to it.
func dashDistDir() string {
	// Priority: env var, ./dist, ../app/dashboard/dist from CWD
	if v := os.Getenv("DASHBOARD_DIST"); v != "" {
		return v
	}
	for _, c := range []string{"dist", "../app/dashboard/dist", "app/dashboard/dist"} {
		if st, err := os.Stat(c); err == nil && st.IsDir() {
			return c
		}
	}
	return "dist"
}

func main() {
	// Graceful termination on SIGTERM/SIGINT too
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sigs
		os.Exit(0)
	}()

	if err := runDesktop(); err != nil {
		slog.Error("desktop shell failed", "err", err)
		os.Exit(1)
	}
}
