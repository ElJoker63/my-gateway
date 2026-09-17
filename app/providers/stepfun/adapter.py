"""StepFun LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import STEPFUN_BASE_URL, STEPFUN_DEFAULT_MODEL

StepFunProvider = build_provider_class(
    name="stepfun",
    base_url=STEPFUN_BASE_URL,
    default_model=STEPFUN_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="StepFunProvider",
)
