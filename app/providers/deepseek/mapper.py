""" Deepseek mapper."""

def map_deepseek_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "deepseek_error",
            "code": status_code,
        }
    }
