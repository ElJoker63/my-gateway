""" Fireworks client wrapper."""
import httpx
from .config import FIREWORKS_BASE_URL

def get_fireworks_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=FIREWORKS_BASE_URL, timeout=timeout)
