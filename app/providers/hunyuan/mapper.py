""" Hunyuan mapper."""

def map_hunyuan_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "hunyuan_error",
            "code": status_code,
        }
    }
