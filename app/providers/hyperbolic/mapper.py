""" Hyperbolic mapper."""

def map_hyperbolic_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "hyperbolic_error",
            "code": status_code,
        }
    }
