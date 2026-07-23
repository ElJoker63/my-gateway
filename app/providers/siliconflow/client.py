""" Siliconflow client wrapper."""
import httpx
from .config import SILICONFLOW_BASE_URL

def get_siliconflow_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=SILICONFLOW_BASE_URL, timeout=timeout)
