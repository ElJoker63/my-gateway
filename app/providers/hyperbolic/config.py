""" Hyperbolic Provider Configuration."""
import os

HYPERBOLIC_BASE_URL = os.getenv("HYPERBOLIC_BASE_URL", "https://api.hyperbolic.xyz/v1")
HYPERBOLIC_DEFAULT_MODEL = os.getenv("HYPERBOLIC_DEFAULT_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
