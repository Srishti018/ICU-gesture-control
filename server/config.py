"""Server configuration, loaded from the repo-root .env (environment variables win)."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

BROKER_HOST = os.getenv("BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
LOGGER_USER = os.getenv("LOGGER_USER", "logger")
LOGGER_PASS = os.getenv("LOGGER_PASS", "")
API_PORT = int(os.getenv("API_PORT", "5050"))
DB_PATH = str(Path(os.getenv("DB_PATH", str(REPO_ROOT / "server" / "icu.db"))).resolve())
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
