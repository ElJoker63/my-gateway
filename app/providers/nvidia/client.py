""" Nvidia client wrapper."""
import httpx
from .config import NVIDIA_BASE_URL

def get_nvidia_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=NVIDIA_BASE_URL, timeout=timeout)
