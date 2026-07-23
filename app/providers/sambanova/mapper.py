""" Sambanova mapper."""

def map_sambanova_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "sambanova_error",
            "code": status_code,
        }
    }
