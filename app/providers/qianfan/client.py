""" Qianfan client wrapper."""
import httpx
from .config import QIANFAN_BASE_URL

def get_qianfan_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=QIANFAN_BASE_URL, timeout=timeout)
