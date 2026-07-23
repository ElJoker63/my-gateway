""" Moonshot mapper."""

def map_moonshot_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "moonshot_error",
            "code": status_code,
        }
    }
