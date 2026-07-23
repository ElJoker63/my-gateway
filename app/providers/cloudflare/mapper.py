""" Cloudflare mapper."""

def map_cloudflare_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "cloudflare_error",
            "code": status_code,
        }
    }
