""" Hunyuan Provider Configuration."""
import os

HUNYUAN_BASE_URL = os.getenv("HUNYUAN_BASE_URL", "https://api.hunyuan.cloud.tencent.com/v1")
HUNYUAN_DEFAULT_MODEL = os.getenv("HUNYUAN_DEFAULT_MODEL", "hunyuan-turbos-latest")
