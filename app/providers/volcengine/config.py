""" Volcengine Provider Configuration."""
import os

VOLCENGINE_BASE_URL = os.getenv("VOLCENGINE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
VOLCENGINE_DEFAULT_MODEL = os.getenv("VOLCENGINE_DEFAULT_MODEL", "doubao-pro-128k")
