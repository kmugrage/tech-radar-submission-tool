import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RADAR_HISTORY_DIR = DATA_DIR / "radar_history"
SUBMISSIONS_FILE = DATA_DIR / "submissions.json"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-sonnet-4-5-20250929")

# Dev mode: set to "true" to use mock responses without an API key
DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")

RADAR_HISTORY_REPO = "setchy/thoughtworks-tech-radar-volumes"
RADAR_HISTORY_BRANCH = "main"
