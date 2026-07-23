"""OpenRouter error mapper."""

def map_openrouter_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "openrouter_error",
            "code": status_code,
        }
    }
