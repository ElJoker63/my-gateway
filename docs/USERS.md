# Multi-User Guide

How each team/friend/agent gets an isolated account with their own provider keys.

## Concepts

- **Master key** (`GATEWAY_API_KEY`) — the superuser. Full access to everything, including
  creating users, listing them, disabling them, rotating keys.
- **User keys** (`gwu_xxx`) — handed out per-account. Work only with that user's
  providers and pools. Rate limits and circuit breakers apply per key.
- **Per-user key pools** — when a user adds provider keys (via `/api/providers/{name}/keys`
  or POST /api/me/keys), the gateway registers them under that user's tenant. Each
  user's keys are isolated: another user never sees them, never uses them.

## Creating a user

```bash
curl -X POST http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

The response includes the raw key **once**:

```json
{
  "user": { "id": "u-…", "name": "Alice", "key_display": "gwu_ab12…" },
  "api_key": "gwu_abcdef1234567890..."
  // shown once — save it!
}
```

## Uso desde el agente (user side)

The user gets the key once and uses it like any other OpenAI-compatible key:

```python
import openai
client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="gwu_abcdef1234567890..."  # her key
)
resp = client.chat.completions.create(
    model="nvidia/Llama-3.3-70B",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

## Rotating a key

Admin only. Old key stops working immediately:

```bash
curl -X POST http://localhost:8000/api/admin/users/u-abc123/rotate \
  -H "Authorization: Bearer $GATEWAY_API_KEY"
```

## Disabling a user

Anything at all stops until re-enabled:

```bash
curl -X DELETE http://localhost:8000/api/admin/users/u-abc123 \
  -H "Authorization: Bearer $GATEWAY_API_KEY"
```

## Security model

| Protects | How |
|----------|-----|
| Master key stored in plaintext at rest | Never — only the hashed form (`sha256`) is persisted |
| User provider keys | AES-256-GCM encrypted using `GATEWAY_MASTER_KEY` |
| Key display in logs | Only the masked form (`gwu_ab12…cd`) ever appears |
| Brute-force on keys | AuthLimiter: 20 failed attempts/minute per source IP |
| Cross-user key visibility | Redis pools are tenant-scoped (`gw:keys:{tenant}:{provider}:*`) |

The master encryption key (`GATEWAY_MASTER_KEY`) never leaves the server; if you lose
it, stored user keys are unrecoverable (that's the point — only the hash is persistent
and the raw key is shown exactly once at creation).
