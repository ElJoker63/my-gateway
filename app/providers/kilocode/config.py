"""Kilocode Provider Configuration."""
import os

KILOCODE_BASE_URL = os.getenv("KILOCODE_BASE_URL", "https://api.kilo.ai/api/openrouter/v1")
KILOCODE_DEFAULT_MODEL = os.getenv("KILOCODE_DEFAULT_MODEL", "anthropic/claude-sonnet-4")
