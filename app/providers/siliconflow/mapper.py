""" Siliconflow mapper."""

def map_siliconflow_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "siliconflow_error",
            "code": status_code,
        }
    }
