""" Lingyiwanwu client wrapper."""
import httpx
from .config import LINGYIWANWU_BASE_URL

def get_lingyiwanwu_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=LINGYIWANWU_BASE_URL, timeout=timeout)
