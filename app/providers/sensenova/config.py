""" Sensenova Provider Configuration."""
import os

SENSENOVA_BASE_URL = os.getenv("SENSENOVA_BASE_URL", "https://api.sensenova.cn/v1")
SENSENOVA_DEFAULT_MODEL = os.getenv("SENSENOVA_DEFAULT_MODEL", "SenseChat-5")
