""" Modelscope client wrapper."""
import httpx
from .config import MODELSCOPE_BASE_URL

def get_modelscope_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=MODELSCOPE_BASE_URL, timeout=timeout)
