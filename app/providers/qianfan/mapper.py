""" Qianfan mapper."""

def map_qianfan_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "qianfan_error",
            "code": status_code,
        }
    }
