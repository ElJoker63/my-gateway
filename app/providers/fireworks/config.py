""" Fireworks Provider Configuration."""
import os

FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
FIREWORKS_DEFAULT_MODEL = os.getenv("FIREWORKS_DEFAULT_MODEL", "accounts/fireworks/models/llama-v3p3-70b-instruct")
