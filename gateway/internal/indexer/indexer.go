// Package indexer walks a project directory, chunks text files, embeds them,
// and stores them as vector memories in Qdrant.
package indexer

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"github.com/ElJoker63/my-gateway/gateway/internal/memory"

	"github.com/redis/go-redis/v9"
)

// Indexer walks local directories.
type Indexer struct {
	Mem          *memory.Service
	Redis        redis.UniversalClient
	MaxFileBytes int
	Ignore       []string
}

// Options control one indexing run.
type Options struct {
	Path        string
	Project     string
	FilePatterns []string
}

// Result summarizes a completed run.
type Result struct {
	Project      string `json:"project"`
	FilesScanned int     `json:"files_scanned"`
	Memories     int     `json:"memories_created"`
	FilesSkipped int     `json:"files_skipped"`
	Errors       int     `json:"errors"`
}

var textExts = map[string]bool{
	".py": true, ".js": true, ".ts": true, ".jsx": true, ".tsx": true,
	".java": true, ".kt": true, ".go": true, ".rs": true,
	".c": true, ".cpp": true, ".h": true, ".hpp": true, ".cs": true,
	".rb": true, ".php": true, ".swift": true, ".scala": true,
	".html": true, ".htm": true, ".css": true, ".scss": true,
	".json": true, ".yaml": true, ".yml": true, ".toml": true, ".ini": true,
	".md": true, ".rst": true, ".txt": true,
	".sh": true, ".bash": true, ".zsh": true, ".ps1": true,
	".sql": true, ".graphql": true, ".xml": true,
}

var knownFilenames = map[string]bool{
	"Dockerfile": true, "Makefile": true, "package.json": true,
	"pyproject.toml": true, "go.mod": true, "go.sum": true,
	"docker-compose.yml": true, "docker-compose.yaml": true,
	".env.example": true, "requirements.txt": true,
}

// Run performs a full index of the path, in batches (no giant whole-file reads).
func (ix *Indexer) Run(ctx context.Context, opts Options) (*Result, error) {
	if ix.Mem == nil {
		return nil, fmt.Errorf("memory service not configured")
	}

	project := opts.Project
	if project == "" {
		project = filepath.Base(filepath.Clean(opts.Path))
	}

	if err := ix.Mem.EnsureCollection(ctx, memory.CollectionName(project)); err != nil {
		return nil, err
	}

	res := &Result{Project: project}
	var points []memory.Point
	entriesSeen := 0

	flush := func() error {
		if len(points) == 0 {
			return nil
		}
		if err := ix.Mem.UpsertBatch(ctx, project, points); err != nil {
			return err
		}
		res.Memories += len(points)
		points = points[:0]
		return nil
	}

	errWalk := filepath.WalkDir(opts.Path, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			res.Errors++
			return nil
		}
		if d.IsDir() {
			if ix.shouldSkipDir(path) {
				return filepath.SkipDir
			}
			return nil
		}
		if !ix.shouldIndex(path, opts.FilePatterns) {
			res.FilesSkipped++
			return nil
		}

		content, err := readFileLimit(path, ix.MaxFileBytes)
		if err != nil {
			res.Errors++
			return nil
		}
		if len(strings.TrimSpace(content)) == 0 {
			res.FilesSkipped++
			return nil
		}

		chunks := chunkText(content, 1500, 200)
		fileType := classifyFile(path)
		relPath, _ := filepath.Rel(opts.Path, path)

		for i, chunk := range chunks {
			header := fmt.Sprintf("File: %s", relPath)
			if len(chunks) > 1 {
				header = fmt.Sprintf("File: %s (chunk %d/%d)", relPath, i+1, len(chunks))
			}
			payload := map[string]any{
				"text":    header + "\n\n" + chunk,
				"file":    relPath,
				"type":    fileType,
				"project": project,
				"metadata": map[string]any{
					"chunk_index":  i,
					"total_chunks": len(chunks),
				},
			}
			points = append(points, memory.Point{Payload: payload})
			entriesSeen++

			// flush in batches of 128
			if len(points) >= 128 {
				if err := flush(); err != nil {
					return err
				}
			}
		}
		res.FilesScanned++
		return nil
	})

	if errWalk != nil {
		return nil, errWalk
	}
	if err := flush(); err != nil {
		return nil, err
	}

	// Persist stats in Redis so the API/UI can read them.
	if ix.Redis != nil {
		_ = ix.Redis.HSet(ctx, "gw:project:stats:"+project, map[string]any{
			"files_indexed":    res.FilesScanned,
			"memories_created": res.Memories,
			"files_skipped":    res.FilesSkipped,
			"errors":           res.Errors,
		}).Err()
	}
	return res, nil
}

// shouldSkipDir applies the ignore list to directory names (anywhere in the
// path, not just the final segment).
func (ix *Indexer) shouldSkipDir(path string) bool {
	parts := strings.Split(filepath.ToSlash(path), "/")
	for _, part := range parts {
		for _, pat := range ix.Ignore {
			if matchPattern(part, pat) {
				return true
			}
		}
	}
	return false
}

func (ix *Indexer) shouldIndex(path string, patterns []string) bool {
	name := filepath.Base(path)
	if len(patterns) > 0 {
		matched := false
		for _, p := range patterns {
			if ok, _ := filepath.Match(p, name); ok {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
	}
	ext := strings.ToLower(filepath.Ext(name))
	if knownFilenames[name] {
		return true
	}
	return textExts[ext]
}

// readFileLimit reads a file and returns an error when it's too large.
func readFileLimit(path string, maxBytes int) (string, error) {
	if maxBytes <= 0 {
		maxBytes = 512 * 1024
	}
	st, err := os.Stat(path)
	if err != nil {
		return "", err
	}
	if st.Size() > int64(maxBytes) {
		return "", fmt.Errorf("file too large: %s", path)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

// chunkText splits a text into roughly equal chunks with overlap on lines.
func chunkText(text string, maxChunk, overlap int) []string {
	if maxChunk <= 0 {
		maxChunk = 1500
	}
	if overlap <= 0 {
		overlap = 200
	}
	lines := strings.Split(text, "\n")
	var chunks []string
	var cur []string
	size := 0

	flush := func() {
		if len(cur) == 0 {
			return
		}
		chunks = append(chunks, strings.Join(cur, "\n"))
	}
	push := func(line string) {
		if size+len(line)+1 > maxChunk && len(cur) > 0 {
			flush()
			// seed next chunk with overlap from the tail of the previous one
			tail := overlappingTail(cur, overlap)
			cur = tail
			size = 0
			for _, l := range tail {
				size += len(l) + 1
			}
		}
		cur = append(cur, line)
		size += len(line) + 1
	}
	for _, l := range lines {
		push(l)
	}
	flush()
	return chunks
}

func overlappingTail(lines []string, overlap int) []string {
	var tail []string
	size := 0
	for i := len(lines) - 1; i >= 0 && size+len(lines[i])+1 <= overlap; i-- {
		tail = append([]string{lines[i]}, tail...)
		size += len(lines[i]) + 1
	}
	return tail
}

// classifyFile returns a simple type label used by the dashboard.
func classifyFile(path string) string {
	name := filepath.Base(path)
	ext := strings.ToLower(filepath.Ext(path))
	lower := strings.ToLower(strings.ReplaceAll(filepath.ToSlash(path), "\\", "/"))

	if knownFilenames[name] || strings.HasPrefix(name, "Dockerfile") {
		return "infrastructure"
	}
	if ext == ".md" || ext == ".rst" || ext == ".txt" || ext == ".adoc" {
		return "documentation"
	}
	if ext == ".json" || ext == ".yaml" || ext == ".yml" || ext == ".toml" || ext == ".ini" || ext == ".cfg" {
		return "config"
	}
	if ext == ".sql" {
		return "database"
	}
	if ext == ".html" || ext == ".htm" || ext == ".css" || ext == ".scss" {
		return "frontend"
	}
	if strings.Contains(lower, "/tests/") || strings.Contains(lower, "/test/") ||
		strings.HasPrefix(name, "test_") || strings.HasSuffix(name, "_test.go") ||
		strings.HasSuffix(name, "_test.py") || strings.HasSuffix(name, "_test.ts") {
		return "test"
	}
	if ext == ".go" || ext == ".py" || ext == ".ts" || ext == ".js" || ext == ".tsx" || ext == ".jsx" ||
		ext == ".java" || ext == ".kt" || ext == ".rs" || ext == ".c" || ext == ".cpp" {
		return "code"
	}
	return "code"
}

func matchPattern(name, pattern string) bool {
	ok, err := filepath.Match(pattern, name)
	if err == nil && ok {
		return true
	}
	return name == pattern
}

// silence unused on slog
var _ = slog.Default
