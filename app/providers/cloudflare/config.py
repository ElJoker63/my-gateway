""" Cloudflare Provider Configuration."""
import os

CLOUDFLARE_BASE_URL = os.getenv("CLOUDFLARE_BASE_URL", "https://api.cloudflare.com/client/v4/accounts")
CLOUDFLARE_DEFAULT_MODEL = os.getenv("CLOUDFLARE_DEFAULT_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
