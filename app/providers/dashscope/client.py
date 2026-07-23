""" Dashscope client wrapper."""
import httpx
from .config import DASHSCOPE_BASE_URL

def get_dashscope_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=DASHSCOPE_BASE_URL, timeout=timeout)
