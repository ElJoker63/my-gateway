""" Fireworks mapper."""

def map_fireworks_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "fireworks_error",
            "code": status_code,
        }
    }
