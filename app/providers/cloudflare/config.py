""" Cloudflare Provider Configuration."""
import os

# Cloudflare Workers AI exposes an OpenAI-compatible endpoint scoped per account:
#   https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
_default_base = (
    f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/v1"
    if CLOUDFLARE_ACCOUNT_ID
    else ""
)
CLOUDFLARE_BASE_URL = os.getenv("CLOUDFLARE_BASE_URL", _default_base)
CLOUDFLARE_DEFAULT_MODEL = os.getenv("CLOUDFLARE_DEFAULT_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")
