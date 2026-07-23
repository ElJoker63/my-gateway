# 🧠 Documentación de My Gateway AI

Bienvenido a la documentación oficial de **My Gateway AI**.

Un gateway inteligente y plataforma de orquestación IA multi-proveedor. Conecta múltiples proveedores de IA, administra llaves de API, maneja rate limits, ofrece enrutamiento inteligente, caché, memoria vectorial e infraestructura de IA escalable.

## ✨ Características Principales

- **Compatible con Múltiples Agentes** — Funciona con Cursor, OpenHands, zcode y cualquier agente compatible con la API de OpenAI
- **Pool y Rotación de Múltiples API Keys** — Balanceo de carga automático, rate limit por key y fallback transparente ante fallos
- **Tres Formatos de API** — `/v1/chat/completions`, `/v1/messages`, `/api/chat`
- **Streaming SSE** — Respuestas en tiempo real para todos los endpoints de chat
- **Caché Inteligente** — Hashing semántico SHA-256 con Redis para evitar peticiones duplicadas
- **Rate Limit Avanzado** — Ventana deslizante por clave con cola de espera automática
- **Memoria Vectorial** — Memoria persistente por proyecto con Qdrant
- **Enriquecimiento de Contexto** — Inyección automática de archivos e información relevante
- **Indexador de Proyectos** — Escaneo e indexación automática de código fuente
- **Soporte Multi-Proveedor** — NVIDIA API, OpenAI, Groq, Ollama Cloud (y servidores remotos)
- **Dockerizado** — Despliegue con un solo comando

---

## 🚀 Navegación Rápida

- [Arquitectura del Sistema](ARCHITECTURE.es.md) — Diagramas de flujo y componentes
- [Referencia de la API](API.es.md) — Documentación de endpoints y ejemplos
- [Configuración](CONFIGURATION.es.md) — Variables de entorno, claves de API y límites
- [Sistema de Memoria](MEMORY_SYSTEM.es.md) — Búsqueda vectorial e indexación en Qdrant
