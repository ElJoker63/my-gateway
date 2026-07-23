""" Github_models mapper."""

def map_github_models_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "github_models_error",
            "code": status_code,
        }
    }
