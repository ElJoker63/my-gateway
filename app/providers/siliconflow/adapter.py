"""SiliconFlow LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import SILICONFLOW_BASE_URL, SILICONFLOW_DEFAULT_MODEL

SiliconFlowProvider = build_provider_class(
    name="siliconflow",
    base_url=SILICONFLOW_BASE_URL,
    default_model=SILICONFLOW_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="SiliconFlowProvider",
)
