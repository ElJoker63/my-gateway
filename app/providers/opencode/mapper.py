""" Opencode mapper."""

def map_opencode_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "opencode_error",
            "code": status_code,
        }
    }
