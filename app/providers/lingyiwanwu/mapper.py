""" Lingyiwanwu mapper."""

def map_lingyiwanwu_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "lingyiwanwu_error",
            "code": status_code,
        }
    }
