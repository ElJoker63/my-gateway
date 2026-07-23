""" Stepfun client wrapper."""
import httpx
from .config import STEPFUN_BASE_URL

def get_stepfun_client(timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=STEPFUN_BASE_URL, timeout=timeout)
