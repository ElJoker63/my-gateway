""" Volcengine mapper."""

def map_volcengine_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "volcengine_error",
            "code": status_code,
        }
    }
