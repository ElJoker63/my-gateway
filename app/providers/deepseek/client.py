""" Deepseek client wrapper."""
import httpx
from .config import DEEPSEEK_BASE_URL

def get_deepseek_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=DEEPSEEK_BASE_URL, timeout=timeout)
