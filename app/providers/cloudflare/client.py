""" Cloudflare client wrapper."""
import httpx
from .config import CLOUDFLARE_BASE_URL

def get_cloudflare_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=CLOUDFLARE_BASE_URL, timeout=timeout)
