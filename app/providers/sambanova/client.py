""" Sambanova client wrapper."""
import httpx
from .config import SAMBANOVA_BASE_URL

def get_sambanova_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=SAMBANOVA_BASE_URL, timeout=timeout)
