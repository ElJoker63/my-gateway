""" Moonshot client wrapper."""
import httpx
from .config import MOONSHOT_BASE_URL

def get_moonshot_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=MOONSHOT_BASE_URL, timeout=timeout)
