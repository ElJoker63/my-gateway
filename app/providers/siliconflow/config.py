""" Siliconflow Provider Configuration."""
import os

SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
SILICONFLOW_DEFAULT_MODEL = os.getenv("SILICONFLOW_DEFAULT_MODEL", "deepseek-ai/DeepSeek-V3")
