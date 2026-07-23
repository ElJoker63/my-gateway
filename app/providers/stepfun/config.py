""" Stepfun Provider Configuration."""
import os

STEPFUN_BASE_URL = os.getenv("STEPFUN_BASE_URL", "https://api.stepfun.com/v1")
STEPFUN_DEFAULT_MODEL = os.getenv("STEPFUN_DEFAULT_MODEL", "step-2-16k")
