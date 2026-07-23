""" Chutes Provider Configuration."""
import os

CHUTES_BASE_URL = os.getenv("CHUTES_BASE_URL", "https://chutes.ai/v1")
CHUTES_DEFAULT_MODEL = os.getenv("CHUTES_DEFAULT_MODEL", "chutes-llama-3.3-70b")
