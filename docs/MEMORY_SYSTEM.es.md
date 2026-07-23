# Sistema de Memoria Vectorial

**My Gateway AI** utiliza **Qdrant** como base de datos vectorial para almacenar y recuperar la memoria de cada proyecto de forma persistente.

## Funcionamiento

1. **Aislamiento por Proyecto**: Cada proyecto posee su propia colección independiente (`project_{nombre}`).
2. **Embeddings Semánticos**: Transforma fragmentos de código y documentación en vectores (usando un modelo local de `sentence-transformers` o la API de embeddings de NVIDIA).
3. **Enriquecimiento Automático**: Antes de enviar la consulta al LLM, busca fragmentos relevantes y los inyecta en el mensaje del sistema.
4. **Indexador de Proyectos**: Analiza el árbol de directorios, divide los archivos en fragmentos (*chunks*) con solapamiento (*overlap*) e indexa el contenido.
