""" Dashscope mapper."""

def map_dashscope_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "dashscope_error",
            "code": status_code,
        }
    }
