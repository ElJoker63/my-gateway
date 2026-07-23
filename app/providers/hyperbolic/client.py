""" Hyperbolic client wrapper."""
import httpx
from .config import HYPERBOLIC_BASE_URL

def get_hyperbolic_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=HYPERBOLIC_BASE_URL, timeout=timeout)
