""" Qianfan Provider Configuration."""
import os

QIANFAN_BASE_URL = os.getenv("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2")
QIANFAN_DEFAULT_MODEL = os.getenv("QIANFAN_DEFAULT_MODEL", "ernie-4.0-8k-latest")
