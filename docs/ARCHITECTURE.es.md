# Arquitectura del Sistema

## Descripción General

**My Gateway AI** es un **proxy local y middleware inteligente** que se sitúa entre los agentes de código (Cursor, OpenHands, zcode) y los proveedores externos de LLM. No es un simple repetidor HTTP: enriquece, almacena en caché, aplica rate limit por clave y contextualiza cada petición.

## Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    Agentes de IA                    │
│  (Cursor, OpenHands, zcode, CLI, agentes custom)    │
└────────────┬───────────┬───────────┬───────────────┘
             │           │           │
     /v1/chat/completions  /v1/messages  /api/chat
             │           │           │
             ▼           ▼           ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Gateway                    │
│                                                     │
│  ┌──────────┐  ┌───────────────┐  ┌────────────────┐│
│  │ Auth     │  │ Key Manager   │  │ Enrutador      ││
│  │ Middleware│→│ Rotación Keys │→ │ de Peticiones  ││
│  └──────────┘  └───────┬───────┘  └────────┬───────┘│
│                        │                   │        │
│      ┌─────────────────┴───────────────────┘        │
│      │                                              │
│      ▼                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Servicio │  │ Constructor│  │ Servicio de      │   │
│  │ Caché    │  │ Contexto │  │ Memoria          │   │
│  │ (Redis)  │  │          │  │ (Qdrant)         │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────────────┘   │
│       │              │              │                │
│       │         ┌────┘              │                │
│       │         ▼                   │                │
│       │    ┌──────────┐            │                │
│       │    │ Capa de  │◄───────────┘                │
│       │    │ Provider │                             │
│       │    └────┬─────┘                             │
│       │         │                                   │
└───────┼─────────┼───────────────────────────────────┘
        │         │
        ▼         ▼
   ┌────────┐ ┌───────────────────────────┐
   │ Redis  │ │ Proveedores Externos      │
   │        │ │ (NVIDIA/OpenAI/Groq/Cloud)│
   └────────┘ └───────────────────────────┘
```

## Flujo de una Petición

1. **Recepción** → El Gateway recibe la petición en formato OpenAI, Anthropic o simplificado.
2. **Autenticación** → Valida la clave Bearer token o header `X-API-Key`.
3. **Caché** → Genera hash SHA-256 de mensajes + modelo + proyecto. Si existe en Redis, responde de inmediato.
4. **Contexto** → Consulta la memoria vectorial en Qdrant e inyecta los fragmentos relevantes.
5. **Key Manager** → Selecciona la mejor clave de API disponible (`least_used` o `round_robin`) y valida la ventana del rate limit.
6. **Llamada LLM + Fallback** → Envía la petición al proveedor. Si ocurre un error 429 o de autenticación, marca la clave en cooldown y reintenta con la siguiente clave.
7. **Persistencia** → Guarda la respuesta en el caché de Redis y la conversación en la memoria de Qdrant en segundo plano.

## Detalles de Componentes

### Key Manager
Administrador de pools de API keys independiente del proveedor. Gestiona la ventana de rate limit por clave en Redis, la rotación de claves (`least_used` o `round_robin`), el cooldown de claves con error y el reintento automático. Enmascara las claves en logs (`nv-****89ab`).

### Capa de Proveedores (Providers)
Clase abstracta `LLMProvider` con métodos `chat()` y `chat_stream()`. Permite la inyección dinámica de la API key en cada petición.

### Servicio de Caché
Usa Redis con hashing SHA-256 generado a partir de `{mensajes, modelo, proyecto}`. Las peticiones idénticas no consumen créditos de API.

### Memoria Vectorial (Qdrant)
Cada proyecto tiene su propia colección (`project_{nombre}`). Los recuerdos se almacenan como embeddings vectoriales con metadatos.
