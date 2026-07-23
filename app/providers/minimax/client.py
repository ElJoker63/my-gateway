""" Minimax client wrapper."""
import httpx
from .config import MINIMAX_BASE_URL

def get_minimax_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=MINIMAX_BASE_URL, timeout=timeout)
