# Referencia de la API

URL Base: `http://localhost:8000`

## Autenticación

Todos los endpoints (excepto `/health`) requieren autenticación:

```http
Authorization: Bearer <GATEWAY_API_KEY>
```

o bien:

```http
X-API-Key: <GATEWAY_API_KEY>
```

---

## Endpoints de Chat

### POST /v1/chat/completions

Formato compatible con OpenAI. Utilizado por la mayoría de los agentes de código (Cursor, OpenHands, zcode).

**Ejemplo de Petición:**
```json
{
  "model": "meta/llama-3.1-70b-instruct",
  "messages": [
    {"role": "user", "content": "¿Cómo funciona la memoria vectorial?"}
  ],
  "project": "udyat",
  "provider": "nvidia",
  "stream": false
}
```

---

### POST /v1/messages

Formato compatible con la API Messages de Anthropic.

---

### POST /api/chat

Formato simplificado del Gateway. Ideal para scripts o integraciones rápidas.

**Petición:**
```json
{
  "project": "udyat",
  "message": "Analiza la arquitectura del proyecto",
  "provider": "groq"
}
```

---

## Endpoints de Memoria

### POST /api/memory/store
Almacena manualmente una entrada de memoria.

### POST /api/memory/search
Busca recuerdos por similitud semántica.

### GET /api/memory/project/{project}
Lista todos los recuerdos almacenados para un proyecto.

### DELETE /api/memory/project/{project}
Elimina la memoria de un proyecto.

---

## Endpoints de Proyectos

### POST /api/projects/index
Inicia la indexación de un directorio de proyecto en segundo plano.

**Petición:**
```json
{
  "path": "/ruta/al/proyecto",
  "project_name": "udyat"
}
```

### GET /api/projects
Lista todos los proyectos indexados.

---

## Endpoints del Sistema

### GET /health
Verifica el estado de salud de Redis y Qdrant.

### GET /api/keys/status
Muestra el estado en tiempo real de los pools de API keys por proveedor (disponibilidad, requests usados, cooldown).

### GET /api/metrics
Telemetría del gateway: contadores de requests/errores, estadísticas por proveedor, percentiles de latencia (p50/p95/p99 en una ventana rodante) y estados de circuit breaker.

---

## Combos

Los combos aliasan un nombre amigable a una lista ordenada de objetivos provider/modelo.
Usa `model: "combo:<nombre>"` en cualquier endpoint de chat para enrutar por el combo.

Estrategias:

- `strict` — prueba los objetivos en orden, fail over ante errores (por defecto).
- `round_robin` — rota el objetivo inicial entre peticiones.
- `least_used` — empieza por el objetivo con menos uso reciente.
- `race` — lanza hasta `race_size` objetivos en paralelo; gana el primero que responde, el resto se cancela.

### GET /api/combos
```json
{ "combos": [ { "name": "fast", "targets": [ { "provider": "nvidia", "model": "llama-3.3-70b", "weight": 1 } ], "strategy": "race", "race_size": 2 } ], "total": 1 }
```

### POST /api/combos
Crea o reemplaza un combo:
```json
{
  "name": "fast",
  "targets": [ { "provider": "nvidia", "model": "llama-3.3-70b" }, { "provider": "groq" } ],
  "strategy": "race",
  "race_size": 2
}
```

### GET /api/combos/{name}
Obtiene un combo (acepta el nombre con o sin `combo:`).

### DELETE /api/combos/{name}
Elimina un combo.


---

## OAuth

Los providers respaldados por OAuth (Kiro, Antigravity) se autentican por navegador/dispositivo en vez de con claves API estáticas.

### POST /api/oauth/{provider}/start

Inicia el handshake OAuth para `kiro` o `antigravity`. La respuesta varía según el flujo:

**Device code (kiro)** — respuesta:
```json
{
  "provider": "kiro",
  "flow": "device_code",
  "verificationUri": "https://device.sso.us-east-1.amazonaws.com/",
  "userCode": "ABCD-EFGH",
  "expiresIn": 600,
  "interval": 5,
  "state": "..."
}
```

**PKCE (antigravity)** — respuesta:
```json
{
  "provider": "antigravity",
  "flow": "pkce",
  "authUrl": "https://accounts.google.com/o/oauth2/v2/auth?...&code_challenge_method=S256",
  "state": "..."
}
```

### GET /api/oauth/{provider}/poll?state=...

Para device flows. Devuelve 202 (`authorization_pending` / `slow_down`) mientras el usuario no ha consentido, y 200 cuando los tokens están guardados.

### GET /api/oauth/{provider}/callback?code=...&state=...

Callback del flujo PKCE (Google redirige aquí tras el consentimiento).

### GET /api/oauth/status

Estado de la sesión OAuth por provider:

```json
{ "kiro": { "connected": true, "expires_in": 3120 } }
```

### DELETE /api/oauth/{provider}

Desconecta un provider (borra sus tokens almacenados).
