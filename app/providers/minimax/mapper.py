""" Minimax mapper."""

def map_minimax_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "minimax_error",
            "code": status_code,
        }
    }
