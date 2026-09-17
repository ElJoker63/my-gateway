""" Opencode Provider Configuration."""
import os

OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
OPENCODE_DEFAULT_MODEL = os.getenv("OPENCODE_DEFAULT_MODEL", "grok-code-fast-1")
