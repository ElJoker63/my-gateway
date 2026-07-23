""" Chutes mapper."""

def map_chutes_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "chutes_error",
            "code": status_code,
        }
    }
