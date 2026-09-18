// Package config loads gateway settings from the environment.
package config

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Settings is the runtime configuration for the gateway.
type Settings struct {
	// Gateway
	GatewayAPIKey  string
	LogLevel       string
	Host           string
	Port           int
	CORSOrigins    []string
	MaxRequestMB   int
	DefaultProvider string

	// Rate limiting
	MaxRequestsPerMinute int
	RateLimitWaitSecs    int

	// Circuit breaker
	CircuitFailureThreshold int
	CircuitUnhealthySecs    int

	// Redis
	RedisHost     string
	RedisPort     int
	RedisPassword string
	CacheTTLSecs  int

	// Qdrant
	QdrantHost string
	QdrantPort int
	QdrantKey  string

	// Embeddings
	EmbeddingModel       string // "local" | "openai"
	LocalEmbeddingModel  string
	EmbeddingDimension   int

	// Memory context
	MaxContextTokens       int
	MemorySearchTopK       int
	MemoryScoreThreshold   float64

	// Indexing
	AllowedIndexRoots []string
	IgnorePatterns    []string
	MaxFileSizeKB     int

	// Provider keys populated per provider from env
	ProviderKeys    map[string][]string
	ProviderRPMs    map[string]int
	ProviderModels  map[string]string
	ProviderBaseURL map[string]string
}

// Load reads the environment and returns the populated Settings.
func Load() (*Settings, error) {
	s := &Settings{
		GatewayAPIKey:        os.Getenv("GATEWAY_API_KEY"),
		LogLevel:             getenv("LOG_LEVEL", "INFO"),
		Host:                 getenv("GATEWAY_HOST", "0.0.0.0"),
		Port:                 getEnvInt("GATEWAY_PORT", 8000),
		MaxRequestMB:         getEnvInt("MAX_REQUEST_SIZE_MB", 10),
		DefaultProvider:      getenv("DEFAULT_PROVIDER", "nvidia"),
		MaxRequestsPerMinute: getEnvInt("MAX_REQUESTS_PER_MINUTE", 35),
		RateLimitWaitSecs:    getEnvInt("RATE_LIMIT_WAIT_TIMEOUT", 60),
		CircuitFailureThreshold: getEnvInt("CIRCUIT_FAILURE_THRESHOLD", 3),
		CircuitUnhealthySecs:    getEnvInt("CIRCUIT_UNHEALTHY_SECONDS", 60),
		RedisHost:     getenv("REDIS_HOST", "localhost"),
		RedisPort:     getEnvInt("REDIS_PORT", 6379),
		RedisPassword: os.Getenv("REDIS_PASSWORD"),
		CacheTTLSecs:  getEnvInt("CACHE_TTL", 86400),
		QdrantHost: getenv("QDRANT_HOST", "localhost"),
		QdrantPort: getEnvInt("QDRANT_PORT", 6333),
		QdrantKey:  os.Getenv("QDRANT_API_KEY"),
		EmbeddingModel:       getenv("EMBEDDING_MODEL", "local"),
		LocalEmbeddingModel:  getenv("LOCAL_EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"),
		EmbeddingDimension:   getEnvInt("EMBEDDING_DIMENSION", 384),
		MaxContextTokens:     getEnvInt("MAX_CONTEXT_TOKENS", 4000),
		MemorySearchTopK:     getEnvInt("MEMORY_SEARCH_TOP_K", 10),
		MemoryScoreThreshold: getEnvFloat("MEMORY_SCORE_THRESHOLD", 0.5),
		AllowedIndexRoots:    mustJSONList(os.Getenv("ALLOWED_INDEX_ROOTS")),
		IgnorePatterns:       mustJSONList(os.Getenv("INDEX_IGNORE_PATTERNS")),
		MaxFileSizeKB:        getEnvInt("MAX_FILE_SIZE_KB", 500),
		ProviderKeys:    make(map[string][]string),
		ProviderRPMs:    make(map[string]int),
		ProviderModels:  make(map[string]string),
		ProviderBaseURL: make(map[string]string),
	}

	origins := os.Getenv("CORS_ALLOWED_ORIGINS")
	if origins == "" {
		origins = "http://localhost:3000,http://127.0.0.1:3000"
	}
	s.CORSOrigins = strings.Split(origins, ",")

	if len(s.IgnorePatterns) == 0 {
		s.IgnorePatterns = []string{".git", "node_modules", "build", "dist", "venv", "__pycache__"}
	}

	s.loadProviderEnv()
	return s, nil
}

// AuthEnabled is true when a real key protects the gateway.
func (s *Settings) AuthEnabled() bool {
	return s.GatewayAPIKey != "" && s.GatewayAPIKey != "change-me-to-a-secure-key"
}

// loadProviderEnv scans the environment for {PROVIDER}_API_KEY(S), {PROVIDER}_MODEL,
// {PROVIDER}_BASE_URL and {PROVIDER}_RPM_LIMIT.
func (s *Settings) loadProviderEnv() {
	for _, name := range knownProviders {
		upper := strings.ToUpper(name)

		// Keys: JSON array or comma-separated
		if raw := os.Getenv(upper + "_API_KEYS"); raw != "" {
			keys := mustJSONList(raw)
			if len(keys) > 0 {
				s.ProviderKeys[name] = keys
			}
		}
		if len(s.ProviderKeys[name]) == 0 {
			if k := os.Getenv(upper + "_API_KEY"); k != "" {
				s.ProviderKeys[name] = []string{k}
			}
		}
		if rpm := os.Getenv(upper + "_RPM_LIMIT"); rpm != "" {
			if n, err := strconv.Atoi(rpm); err == nil && n > 0 {
				s.ProviderRPMs[name] = n
			}
		}
		if m := os.Getenv(upper + "_MODEL"); m != "" {
			s.ProviderModels[name] = m
		}
		if b := os.Getenv(upper + "_BASE_URL"); b != "" {
			s.ProviderBaseURL[name] = b
		}
	}
}

// KeyFor selects the provider's key set (memory-safe copy).
func (s *Settings) KeysFor(provider string) []string {
	keys, ok := s.ProviderKeys[provider]
	if !ok || len(keys) == 0 {
		return nil
	}
	out := make([]string, len(keys))
	copy(out, keys)
	return out
}

// RPMFor resolves a provider's RPM limit (falls back to global).
func (s *Settings) RPMFor(provider string) int {
	if n, ok := s.ProviderRPMs[provider]; ok && n > 0 {
		return n
	}
	return s.MaxRequestsPerMinute
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(strings.TrimSpace(v)); err == nil {
			return n
		}
	}
	return fallback
}

func getEnvFloat(key string, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(strings.TrimSpace(v), 64); err == nil {
			return f
		}
	}
	return fallback
}

// mustJSONList parses JSON array "[]"-style or comma-separated strings from env.
func mustJSONList(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	var out []string
	if err := json.Unmarshal([]byte(raw), &out); err == nil {
		return out
	}
	// Fallback: comma-separated
	parts := strings.Split(raw, ",")
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// knownProviders is the static registry of supported provider names.
var knownProviders = []string{
	"nvidia", "openai", "groq", "ollama", "openrouter", "google",
	"cloudflare", "github_models", "sambanova", "chutes", "fireworks",
	"hyperbolic", "opencode", "opencode_go", "deepseek", "siliconflow",
	"modelscope", "zhipu", "moonshot", "minimax", "dashscope", "hunyuan",
	"qianfan", "sensenova", "stepfun", "lingyiwanwu", "volcengine",
	"kilocode", "kiro", "antigravity", "nous_research",
}

// ProviderNames returns all known provider slugs.
func ProviderNames() []string {
	out := make([]string, len(knownProviders))
	copy(out, knownProviders)
	return out
}

// Validate returns an error for obviously broken settings.
func (s *Settings) Validate() error {
	if s.Port <= 0 || s.Port > 65535 {
		return fmt.Errorf("invalid GATEWAY_PORT %d", s.Port)
	}
	if s.MaxRequestMB <= 0 {
		return fmt.Errorf("MAX_REQUEST_SIZE_MB must be positive")
	}
	return nil
}
