""" Sensenova mapper."""

def map_sensenova_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "sensenova_error",
            "code": status_code,
        }
    }
