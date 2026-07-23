"""Groq request and error mapper."""

def map_groq_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "groq_error",
            "code": status_code,
        }
    }
