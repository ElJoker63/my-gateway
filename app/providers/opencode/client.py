""" Opencode client wrapper."""
import httpx
from .config import OPENCODE_BASE_URL

def get_opencode_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=OPENCODE_BASE_URL, timeout=timeout)
