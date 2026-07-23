"""Groq client wrapper."""
import httpx
from .config import GROQ_BASE_URL

def get_groq_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=GROQ_BASE_URL, timeout=timeout)
