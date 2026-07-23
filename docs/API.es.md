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
