""" Github_models client wrapper."""
import httpx
from .config import GITHUB_MODELS_BASE_URL

def get_github_models_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=GITHUB_MODELS_BASE_URL, timeout=timeout)
