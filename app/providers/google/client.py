"""Google AI Studio client wrapper."""
import httpx
from .config import GOOGLE_BASE_URL

def get_google_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=GOOGLE_BASE_URL, timeout=timeout)
