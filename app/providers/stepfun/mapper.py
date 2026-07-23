""" Stepfun mapper."""

def map_stepfun_error(status_code: int, detail: str) -> dict:
    return {
        "error": {
            "message": detail,
            "type": "stepfun_error",
            "code": status_code,
        }
    }
