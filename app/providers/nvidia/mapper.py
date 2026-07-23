""" Nvidia mapper."""

def map_nvidia_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "nvidia_error",
            "code": status_code,
        }
    }
