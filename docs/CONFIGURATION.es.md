# Configuración del Sistema

Toda la configuración se gestiona mediante variables de entorno en el archivo `.env`.

## Variables de Entorno principales

### Gateway

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `GATEWAY_API_KEY` | `change-me-to-a-secure-key` | Clave de API local para autenticar peticiones al Gateway |
| `DEFAULT_PROVIDER` | `nvidia` | Proveedor por defecto cuando no se especifica en la petición |
| `MAX_REQUESTS_PER_MINUTE` | `35` | Límite de peticiones por minuto por defecto (RPM) |

### Proveedores y Pools de API Keys

#### NVIDIA
```env
NVIDIA_API_KEY=nvapi-key1
# O pool con múltiples keys:
NVIDIA_API_KEYS=["nvapi-key1", "nvapi-key2"]
NVIDIA_RPM_LIMIT=35
```

#### OpenAI
```env
OPENAI_API_KEY=sk-key1
OPENAI_API_KEYS=["sk-key1", "sk-key2"]
OPENAI_RPM_LIMIT=500
```

#### Groq
```env
GROQ_API_KEY=gsk_key1
GROQ_API_KEYS=["gsk_key1", "gsk_key2"]
GROQ_RPM_LIMIT=30
```

#### Ollama Cloud
```env
OLLAMA_API_KEY=ollama_key1
OLLAMA_BASE_URL=https://ollama.com/v1
OLLAMA_RPM_LIMIT=0
```

### Gestión de Claves y Rotación

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `KEY_SELECTION_STRATEGY` | `least_used` | Estrategia de rotación: `least_used` (balanceo por uso) o `round_robin` |
| `KEY_ERROR_COOLDOWN` | `60` | Tiempo de enfriamiento en segundos tras un error 429 o fallo de auth |
