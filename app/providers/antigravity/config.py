"""Antigravity Provider Configuration."""
import os

ANTIGRAVITY_BASE_URL = os.getenv("ANTIGRAVITY_BASE_URL", "https://daily-cloudcode-pa.googleapis.com")
ANTIGRAVITY_DEFAULT_MODEL = os.getenv("ANTIGRAVITY_DEFAULT_MODEL", "gemini-3.1-pro-agent")
