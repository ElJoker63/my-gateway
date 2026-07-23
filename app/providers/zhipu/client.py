""" Zhipu client wrapper."""
import httpx
from .config import ZHIPU_BASE_URL

def get_zhipu_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=ZHIPU_BASE_URL, timeout=timeout)
