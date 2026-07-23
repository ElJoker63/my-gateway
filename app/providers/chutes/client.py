""" Chutes client wrapper."""
import httpx
from .config import CHUTES_BASE_URL

def get_chutes_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=CHUTES_BASE_URL, timeout=timeout)
