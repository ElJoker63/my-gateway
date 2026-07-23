""" Opencode Provider Configuration."""
import os

OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://api.opencode.ai/v1")
OPENCODE_DEFAULT_MODEL = os.getenv("OPENCODE_DEFAULT_MODEL", "opencode-coder-70b")
