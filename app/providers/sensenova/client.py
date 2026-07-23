""" Sensenova client wrapper."""
import httpx
from .config import SENSENOVA_BASE_URL

def get_sensenova_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=SENSENOVA_BASE_URL, timeout=timeout)
