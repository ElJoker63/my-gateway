"""OpencodeGo Provider Configuration."""
import os

OPENCODE_GO_BASE_URL = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
OPENCODE_GO_DEFAULT_MODEL = os.getenv("OPENCODE_GO_DEFAULT_MODEL", "grok-code-fast-1")
