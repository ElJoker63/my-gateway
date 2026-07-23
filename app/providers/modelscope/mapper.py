""" Modelscope mapper."""

def map_modelscope_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "modelscope_error",
            "code": status_code,
        }
    }
