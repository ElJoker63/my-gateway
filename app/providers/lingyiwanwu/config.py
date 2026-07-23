""" Lingyiwanwu Provider Configuration."""
import os

LINGYIWANWU_BASE_URL = os.getenv("LINGYIWANWU_BASE_URL", "https://api.lingyiwanwu.com/v1")
LINGYIWANWU_DEFAULT_MODEL = os.getenv("LINGYIWANWU_DEFAULT_MODEL", "yi-lightning")
