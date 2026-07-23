# Memory System

The AI Agent Gateway uses **Qdrant** as a persistent vector database to maintain project-specific memory. This enables the gateway to automatically enrich LLM requests with relevant context from your codebase and past conversations.

## How It Works

### Storage Model

Each memory entry is stored as a vector embedding with a metadata payload:

```json
{
  "vector": [0.123, -0.456, ...],   // 384-dim embedding
  "payload": {
    "text": "The User model has fields: id, email, password_hash",
    "project": "udyat",
    "file": "models/user.py",
    "type": "code",
    "timestamp": "2024-01-15T10:30:00Z",
    "metadata": {}
  }
}
```

### Collections

Each project gets its own Qdrant collection:
- `project_udyat`
- `project_chatapp`
- `project_server`

This ensures complete isolation between projects.

### Memory Types

| Type | Description | Example |
|------|-------------|---------|
| `code` | Source code content | Function implementations |
| `documentation` | README, docs, comments | API documentation |
| `architecture` | System design decisions | Database schema choices |
| `config` | Configuration files | Docker, environment settings |
| `decision` | Technical decisions | "We chose MongoDB because..." |
| `conversation` | Past Q&A exchanges | Auto-stored from chat |
| `infrastructure` | DevOps/deployment | Dockerfile, CI/CD configs |
| `dependencies` | Package manifests | requirements.txt content |
| `test` | Test files | Test cases and assertions |
| `database` | SQL/schema files | Migration scripts |
| `frontend` | UI code | HTML/CSS/JS files |
| `general` | Everything else | Miscellaneous context |

## Embedding

### Local Model (Default)

Uses `sentence-transformers/all-MiniLM-L6-v2`:
- **Dimension**: 384
- **Speed**: ~1000 embeddings/second on CPU
- **Cost**: Free (runs in gateway container)
- **Quality**: Good for code and technical content

### NVIDIA API (Optional)

Uses `nvidia/nv-embedqa-e5-v5`:
- **Dimension**: 1024
- **Speed**: Network-dependent
- **Cost**: Uses API credits
- **Quality**: Higher accuracy for complex queries

Set `EMBEDDING_MODEL=nvidia` in `.env` to use.

## Project Indexing

### How to Index

```bash
curl -X POST http://localhost:8000/api/projects/index \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/path/to/your/project",
    "project_name": "udyat",
    "file_patterns": ["*.py", "*.js", "*.md"]
  }'
```

### What Gets Indexed

The indexer scans all text/code files and creates chunked embeddings:

1. **Walks the directory tree** (respects ignore patterns)
2. **Filters by extension** — `.py`, `.js`, `.ts`, `.md`, `.yaml`, etc.
3. **Chunks large files** — 1500 chars per chunk with 200 char overlap
4. **Generates embeddings** — Batch processing for efficiency
5. **Stores in Qdrant** — With file path, type, and metadata

### Ignored Patterns

By default, the indexer ignores:
- `.git`, `node_modules`, `build`, `dist`, `venv`
- `__pycache__`, `.env`, `.venv`
- `*.pyc`, `*.pyo`, `.DS_Store`
- Files larger than 500KB

## Context Enrichment

### Automatic Context Injection

When a chat request includes a `project` name, the gateway automatically:

1. Takes the user's latest message
2. Generates an embedding for semantic search
3. Queries the project's Qdrant collection
4. Filters results by relevance score (default threshold: 0.5)
5. Formats the top results into a context block
6. Injects it as a system message in the conversation

### Example

**User sends:**
```
"Modify the song cancellation system"
```

**Gateway searches and finds:**
```
[CODE] (models/song.py) [relevance: 0.89]
class Song(BaseModel):
    id: str
    title: str
    status: str  # active, cancelled, archived

[ARCHITECTURE] [relevance: 0.82]
The song cancellation flow: user requests cancel → validate ownership →
update status → notify streaming service → log event

[CONVERSATION] [relevance: 0.75]
Q: How does the streaming queue work?
A: Songs are queued in Redis with TTL...
```

**What the LLM receives:**
```
System: [Gateway Context — Project: udyat]
The following is relevant context retrieved from the project's memory...

[CODE] (models/song.py) [relevance: 0.89]
class Song(BaseModel): ...

[ARCHITECTURE] [relevance: 0.82]
The song cancellation flow: ...

User: Modify the song cancellation system
```

## Data Persistence

All Qdrant data is persisted to `./data/qdrant/` via Docker volume mount. Data survives container restarts and rebuilds.

### Backup

```bash
# Simply copy the data directory
cp -r ./data/qdrant ./backup/qdrant-$(date +%Y%m%d)
```

### Reset

```bash
# Delete all memory data
rm -rf ./data/qdrant
docker compose restart qdrant
```
