""" Sambanova Provider Configuration."""
import os

SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1")
SAMBANOVA_DEFAULT_MODEL = os.getenv("SAMBANOVA_DEFAULT_MODEL", "Meta-Llama-3.3-70B-Instruct")
