""" Minimax Provider Configuration."""
import os

MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
MINIMAX_DEFAULT_MODEL = os.getenv("MINIMAX_DEFAULT_MODEL", "MiniMax-Text-01")
