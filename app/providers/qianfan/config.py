""" Qianfan Provider Configuration."""
import os

QIANFAN_BASE_URL = os.getenv("QIANFAN_BASE_URL", "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop")
QIANFAN_DEFAULT_MODEL = os.getenv("QIANFAN_DEFAULT_MODEL", "ERNIE-4.0-8K")
