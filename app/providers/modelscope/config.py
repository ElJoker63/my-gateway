""" Modelscope Provider Configuration."""
import os

MODELSCOPE_BASE_URL = os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1")
MODELSCOPE_DEFAULT_MODEL = os.getenv("MODELSCOPE_DEFAULT_MODEL", "Qwen/Qwen2.5-72B-Instruct")
