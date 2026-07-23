"""Google AI Studio mapper."""

def map_google_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "google_api_error",
            "code": status_code,
        }
    }
