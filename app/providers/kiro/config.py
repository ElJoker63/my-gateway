"""Kiro Provider Configuration."""
import os

KIRO_REGION = os.getenv("KIRO_REGION", "us-east-1")
KIRO_BASE_URL = os.getenv(
    "KIRO_BASE_URL",
    f"https://codewhisperer.{KIRO_REGION}.amazonaws.com",
)
KIRO_DEFAULT_MODEL = os.getenv("KIRO_DEFAULT_MODEL", "claude-sonnet-4.5")
