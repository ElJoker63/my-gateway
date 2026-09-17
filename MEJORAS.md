# Plan de mejora — My Gateway AI

> ✅ **Estado:** las 33 tareas (T1–T33) están resueltas en `main`. Cada commit
> referencia su tarea en el mensaje; la suite completa (pytest, ruff) pasa.
>
> Resumen: auth obligatoria con aviso si se desactiva, indexing restringido a
> `ALLOWED_INDEX_ROOTS`, IO asíncrono real (AsyncQdrantClient + hilos para
> embeddings), ids de llave únicos con adquisición atómica vía Lua, adapters
> generados por factoría, endpoints de providers corregidos, CI real,
> Dockerfile multi-stage con usuario no-root.

---

> Comparativa inicial (2026-09-16) — lo que la auditoría encontró:


Leyenda de prioridad:

- 🔴 **P0 — Crítico**: agujero de seguridad o bug que rompe funcionamiento en producción.
- 🟠 **P1 — Importante**: comportamiento incorrecto, falsos positivos, deuda que engaña.
- 🟡 **P2 — Mejora**: calidad, rendimiento, mantenibilidad.
- 🔵 **P3 — Proceso**: tooling, CI, cobertura de tests.

---

## 🔴 P0 — Seguridad y fallos críticos

### ✅ T1. Arreglar el middleware de autenticación
`app/main.py:131-166`
- Si `GATEWAY_API_KEY` conserva el valor por defecto, la auth **se desactiva en silencio** — ni siquiera un log de advertencia.
- Las claves `nvidia_api_key` / `openai_api_key` se aceptan como credenciales del gateway: una key de backend de un proveedor funciona como llave maestra.
- Si `nvidia_api_key` u `openai_api_key` están vacías (`""`), una petición **sin header de auth** pasa (`"" in {"", ...}`).
- Rechazar peticiones sin key cuando hay key configurada; nunca aceptar keys de proveedores como auth del gateway; loguear warning fuerte (o negarse a arrancar) con la key por defecto.

### ✅ T2. Path traversal en la indexación de proyectos
`app/api/projects.py:24-58`, `app/models/requests.py:126`, `app/workers/tasks.py:134-236`
- `ProjectIndexRequest.path` acepta cualquier ruta absoluta sin allowlist. Un cliente autenticado puede indexar `C:\Windows` o `/etc` y luego leer su contenido vía `/api/memory/search`.
- Añadir una lista de directorios raíz permitidos (config), resolver con `Path.resolve()` y rechazar lo que esté fuera.

### ✅ T3. Limitar el tamaño de los requests
`app/main.py`, `app/models/requests.py:52-100`
- No hay middleware de límite de body; `max_request_size_mb` existe en config pero **no se usa**. `messages`/`message` tampoco tienen `max_length`.
- Un body gigante tumba Redis (caché), Qdrant y la RAM del proceso → DoS trivial.
- Implementar el middleware de límite usando `settings.max_request_size_mb` y añadir `max_length` a los strings de los modelos.

### ✅ T4. El indexado de proyectos bloquea todo el servidor
`app/workers/tasks.py:134-236`, `app/api/projects.py:24-58`
- `index_project_task` es `async` pero todo su trabajo es síncrono (`os.walk`, `open().read()` por archivo). Lanzado con `BackgroundTasks` corre **en el mismo event loop** y congela el gateway durante minutos.
- Ejecutar en thread pool (`asyncio.to_thread` / `run_in_executor`) o en worker real (Celery/Arq), y procesar por lotes.

### ✅ T5. Embeddings locales bloquean el event loop
`app/services/embedding.py:26,58-69`
- `model.encode()` (CPU-bound, cientos de ms) se llama directamente en código async; la primera llamada además carga SentenceTransformer entero en el loop.
- Todo `/chat` con `use_memory=True` congela el servidor.
- Envolver en `asyncio.to_thread()` y precargar el modelo en el lifespan.

### ✅ T6. Cliente Qdrant síncrono usado en código async
`app/database/qdrant.py:50`, `app/services/memory.py:56-253`
- `QdrantClient` es síncrono y se usa en todas las funciones async (`upsert`, `search`, `scroll`…): cada operación de memoria bloquea el event loop en una llamada de red.
- Usar `AsyncQdrantClient` (disponible en `qdrant-client`) o `asyncio.to_thread`.

### ✅ T7. CORS con wildcard + credenciales
`app/main.py:106-113`
- `allow_origins=["*"]` junto a `allow_credentials=True` es una combinación inválida/insegura. Definir orígenes explícitos por configuración.

---

## 🟠 P1 — Correctitud

### ✅ T8. Eliminar el sombreado groq.py / nvidia.py / (ollama.py, openai.py)
`app/providers/`
- Existen `groq.py` y `nvidia.py` (módulos legacy) **junto a** los paquetes `groq/` y `nvidia/`. Python sombrea el módulo con el paquete: los `.py` son código muerto inalcanzable (verificado por resolución de imports), pero confunden y se compilan en `__pycache__`.
- Borrar los módulos legacy (o reintegrar lo valioso en los paquetes) y unificar criterio para `openai.py`/`ollama.py` vs paquetes.

### ✅ T9. Los providers no reciben sus API keys
`app/providers/__init__.py:84-94`
- Ningún `config.py` de paquete lee `*_API_KEY`; `init_providers()` instancia `provider_cls()` sin argumentos → `default_api_key=""` → si el caller no pasa `api_key`, la petición sale con `Bearer ""`.
- Pasar las keys (o un getter de key) del KeyManager/settings al constructor del adapter.

### ✅ T10. Providers rotos que heredan OpenAIAdapter tal cual
- **qianfan** (`adapter.py`): Baidu Qianfan usa OAuth `access_token` en querystring y rutas `/chat/{model}`; enviarle Bearer `/chat/completions` está roto.
- **sensenova** (`adapter.py`): SenseNova requiere firma HMAC, no Bearer. Roto.
- **cloudflare** (`adapter.py`): falta `account_id` en la URL de Workers AI. Roto.
- **hunyuan** (`config.py:4`): endpoint dudoso (`api.hunyuan.tencent.com/v1` vs el real `api.hunyuan.cloud.tencent.com`).
- **opencode** (`config.py`, `metadata.json`): URL y modelo parecen inventados (opencode.ai no expone esa API). Verificar o eliminar.
- Marcar estos providers como no soportados o implementar adapters específicos.

### ✅ T11. `health_check` de providers es siempre True (falso positivo)
`app/providers/openai_adapter.py:176`
- `list_models()` captura excepciones y devuelve `[]` en error; `health_check` devuelve `True` aunque el provider esté caído. Rehacer con una petición mínima con `raise_for_status`.

### ✅ T12. `embeddings` usa un modelo de OpenAI para todos los providers
`app/providers/openai_adapter.py:155`
- Default `"text-embedding-3-small"` para nvidia, zhipu, etc. Pedir el modelo por metadata/config del provider o rechazar si `capabilities.embeddings` es false.

### ✅ T13. Race condition (TOCTOU) en la adquisición de keys
`app/services/key_manager.py:163-231`
- `_get_key_status` y `_consume_slot` son llamadas Redis separadas: N corrutinas ven la misma key "libre". El script Lua absorbe el exceso pero su retorno se ignora (L335). Además el SHA cacheado rompe tras `SCRIPT FLUSH`/restart (→ fail-open silencioso del rate limit).
- Hacer la selección+consumo atómica en un solo script Lua y recargar el script ante `NOSCRIPT`.

### ✅ T14. `mask_key` colisiona como identificador
`app/services/key_manager.py:52-56,353-369`
- Dos keys con mismos 3 primeros + 4 últimos caracteres comparten `key_id` → el cooldown se aplica a la key equivocada. Usar hash (sha256 corto) del key completo como ID interno.

### ✅ T15. La clave de caché ignora parámetros de generación
`app/services/cache.py:21-37`, `app/api/chat.py:148-195`
- La key solo incluye `messages + model + project`: dos peticiones iguales pero con distinto `temperature`/`top_p`/`max_tokens`/`tools` devuelven la misma respuesta cacheada. Incluir los params efectivos en el hash.

### ✅ T16. Colisión de colecciones de memoria entre proyectos
`app/services/memory.py:28-32`
- `"my-project"`, `"my_project"` y `"My Project"` mapean a la misma colección → proyectos distintos comparten memoria y se borran mutuamente. Usar el nombre exacto (o hash) en el nombre de colección.

### ✅ T17. Mensajes multimodales rompen la memoria y el contexto
`app/api/chat.py:538-563`, `app/services/context.py:44-46`
- `ChatMessage.content` puede ser lista de bloques; `_store_conversation_memory` guarda basura (`Q: [{'type': ...}]`) y `build_context` pasa una lista al embedder (la excepción es tragada → contexto vacío). Normalizar: extraer solo bloques de texto.

### ✅ T18. Reparar los tests rotos de la API
`tests/test_api.py:33,58,110`
- `patch("app.api.chat.rate_limiter")` y `patch("app.api.chat.list_providers")` apuntan a símbolos que ya no existen allí (residuo de refactor) → `AttributeError`.
- Añadir tests del caso 401 del middleware de auth (hoy solo se prueba el happy path).

### ✅ T19. `init_redis`/`init_qdrant` no verifican conexión de verdad
`app/database/redis.py:33-47`, `app/database/qdrant.py:36-52`
- Sin `ping()`, el arranque loguea "✓ connected" aunque el servicio esté caído. Hacer ping real y fallar (o degradar explícitamente) con advertencia visible.

### ✅ T20. Fuga de errores internos al cliente
`app/api/chat.py:105-112,231-273`, `app/api/memory.py:43,66,84`
- `HTTPException(detail=str(e))` expone mensajes de providers, rutas internas y posibles fragmentos de request/keys. Devolver mensajes genéricos y loguear el detalle internamente.

---

## 🟡 P2 — Deuda técnica y rendimiento

### ✅ T21. Eliminar código muerto masivo
- `app/services/rate_limit.py` (203 líneas): el singleton no lo usa nadie; duplica el Lua de `key_manager.py`. Además `tests/test_rate_limit.py` da falsa cobertura de código que nunca corre.
- `app/services/model_sync.py`: solo se usa `register_provider_metadata`; el resto es caché huérfana.
- `invalidate_project_cache` (`cache.py:104-121`): roto — el set `gw:cache:project:*` nunca se puebla.
- `client.py`, `mapper.py`, `models.py` de **todos** los paquetes de providers: no los importa nadie.
- `extract_search_terms` (`context.py:136-156`): nunca llamado.
- `files_indexed=0` hardcodeado en `app/api/projects.py:68-77`.

### ✅ T22. Factorizar los 23 adapters idénticos
`app/providers/*/adapter.py`
- 23 adapters byte-a-byte idénticos salvo nombre/config → una factoría `make_openai_compatible(name, config, metadata)` y borrar los esqueletos. Mantener solo customizaciones reales (ej. `openrouter` con `extra_headers`).

### ✅ T23. Falso batching y bypass del KeyManager en embeddings NVIDIA
`app/services/embedding.py:52-53`
- N requests HTTP secuenciales en vez de una llamada por lote; cliente nuevo por llamada (sin keep-alive); key leída directa de settings (sin rotación ni cooldown). Solución: batching real + cliente compartido + KeyManager.

### ✅ T24. Parámetros aceptados y silenciosamente descartados
`app/models/requests.py:52-72`, `app/api/chat.py:297-301`
- `frequency_penalty`, `presence_penalty`, `n`, `user` se validan y luego no se reenvían al provider. Reenviarlos o rechazarlos explícitamente.

### ✅ T25. Serie de micro-mejoras de servicios
- `key_manager.py:195-218`: sondeo secuencial de estado de keys → `asyncio.gather`/pipeline.
- `qdrant.py:64-81`: `ensure_collection` hace `get_collections()` en cada `store_memory` → cachear en memoria.
- `projects.py:68-77`: N+1 en `GET /api/projects`.
- `model_sync.py`: `/v1/models` (`chat.py:509-530`) ignora la caché y solo devuelve `default_model`.
- Estrategia "fail-open" (cache, key manager, rate limit) sin métrica ni alerta: documentarla o hacerla configurable.

### ✅ T26. Bugs de plataforma / obsolescencia
- `workers/tasks.py:87`: detección de tests por `"/tests/"` falla en Windows (`\`).
- `workers/tasks.py`: el índice acumula todo en RAM antes de embedir (OOM en repos grandes); `_chunk_text` ignora el límite de tokens del embedder.
- `responses.py:147`: `datetime.utcnow()` deprecado → `datetime.now(timezone.utc)`.
- `AnthropicContentBlock` duplicado en `requests.py:77` y `responses.py:78`.
- Estimación de tokens `tokens*4` (`context.py:78`) burda para código — considerar tokenizer real (tiktoken) o límite conservador.

### ✅ T27. `config.py` no escala a 24 providers
`app/config.py`
- Solo 4 providers (nvidia, openai, groq, ollama) tienen campos tipados; los otros 20 dependen de `getattr` dinámico con defaults vacíos y del validator que solo cubre 4 listas de keys.
- Generalizar a una tabla de providers (`dict[str, ProviderSettings]`) con validación homogénea.

---

## 🔵 P3 — Proceso y tooling

### ✅ T28. CI: el único workflow despliega documentación; no corre tests ni lint
`.github/workflows/deploy-docs.yml`
- Añadir workflow con: `ruff` (lint+format), `pytest` (unit), y `pip-audit`/Aikido para dependencias. Fallar en verde-rojo de tests.

### ✅ T29. Dependencias sin pinear
`requirements.txt`
- Versiones `>=` sin lock; construir con constraints (`uv pip compile` / `pip-tools`) o pasar a `pyproject.toml` + lock. Añadir `pyproject.toml` con config de ruff/pytest/mypy.

### ✅ T30. Normalizar la estructura de tests de providers
`app/providers/*/tests/`
- 21 paquetes tienen un único test idéntico sin `__init__.py` que solo verifica name/default_model; google/groq/openrouter/openai/ollama no tienen ninguno.
- Consolidar en `tests/providers/` un test paramétrico por provider + tests con httpx mockeado que habrían detectado T10/T11/T12.

### ✅ T31. Cobertura de escenarios reales
`tests/`
- Hoy no hay tests de: streaming SSE, fallback multi-key, inyección de contexto/memoria, indexación, auth negativa, ni comportamiento con Redis/Qdrant caídos. Todo es mock sobre mock — priorizar tests de integración con `httpx.MockTransport` y fakes de Redis/Qdrant.

### ✅ T32. Dockerfile endurecido
`Dockerfile`
- Corre como root; sin usuario no-root, sin multi-stage (compilación y runtime mezclados). Crear `USER`, multi-stage, y no copiar `.env` al contexto (`.dockerignore` lo incluye — verificar).

### ✅ T33. Docs y metadatos desincronizados
- `default_provider` docstring dice "(nvidia, openai)" pero hay 24 providers; el endpoint de estado (`/api/keys/status`) importa dentro del handler para evitar ciclos — revisar interdependencias.
- Health devuelve `version="1.0.0"` hardcodeada en dos sitios (`main.py:94,196`) — unificar en una constante.

---

## Resumen

| Prioridad | Tareas | Tema dominante |
|-----------|--------|----------------|
| 🔴 P0 | T1–T7 | Auth rota, path traversal, DoS por body, event loop bloqueado |
| 🟠 P1 | T8–T20 | Providers sin keys/rotos, falsos positivos de salud, carreras, tests rotos |
| 🟡 P2 | T21–T27 | Código muerto, duplicación masiva, rendimiento |
| 🔵 P3 | T28–T33 | CI inexistente, deps sin pinear, Docker como root |

**Orden sugerido de ejecución:** T1 → T2 → T3 (seguridad) → T4/T5/T6 (estabilidad del servidor) → T9/T10/T11 (que los providers funcionen de verdad) → T13–T18 → deuda (T21/T22) → proceso (T28–T33).
