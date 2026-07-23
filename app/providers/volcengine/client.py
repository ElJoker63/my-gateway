""" Volcengine client wrapper."""
import httpx
from .config import VOLCENGINE_BASE_URL

def get_volcengine_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=VOLCENGINE_BASE_URL, timeout=timeout)
