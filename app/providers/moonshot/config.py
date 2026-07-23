""" Moonshot Provider Configuration."""
import os

MOONSHOT_BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
MOONSHOT_DEFAULT_MODEL = os.getenv("MOONSHOT_DEFAULT_MODEL", "moonshot-v1-128k")
