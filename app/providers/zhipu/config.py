""" Zhipu Provider Configuration."""
import os

ZHIPU_BASE_URL = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_DEFAULT_MODEL = os.getenv("ZHIPU_DEFAULT_MODEL", "glm-4-plus")
