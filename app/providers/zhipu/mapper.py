""" Zhipu mapper."""

def map_zhipu_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "zhipu_error",
            "code": status_code,
        }
    }
