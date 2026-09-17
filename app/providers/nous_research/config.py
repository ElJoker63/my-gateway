"""NousResearch Provider Configuration."""
import os

NOUS_RESEARCH_BASE_URL = os.getenv("NOUS_RESEARCH_BASE_URL", "https://inference-api.nousresearch.com/v1")
NOUS_RESEARCH_DEFAULT_MODEL = os.getenv("NOUS_RESEARCH_DEFAULT_MODEL", "hermes-3-llama-3.1-70b")
