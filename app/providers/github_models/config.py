""" Github_models Provider Configuration."""
import os

GITHUB_MODELS_BASE_URL = os.getenv("GITHUB_MODELS_BASE_URL", "https://models.inference.ai.azure.com")
GITHUB_MODELS_DEFAULT_MODEL = os.getenv("GITHUB_MODELS_DEFAULT_MODEL", "gpt-4o")
