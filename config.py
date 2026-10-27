"""
config.py
---------
Centralises all configurable constants and loads environment variables from
the .env file (if present).  Nothing here touches Streamlit or business logic.
"""

import os
# pyrefly: ignore[missing-import]
from dotenv import load_dotenv

# Load .env file if it exists; silently skip if absent
load_dotenv()

# ---------------------------------------------------------------------------
# API keys (populated in Phase 2)
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Gemini model to use for caption generation.
# Override via GEMINI_MODEL env var if you want to use a different model.
# gemini-3.8-flash supports JSON output mode and is fast for structured tasks.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# ---------------------------------------------------------------------------
# Gemini request reliability
# ---------------------------------------------------------------------------
# Hard wall-clock timeout for a single Gemini HTTP call, in milliseconds.
# 503/429 responses are retried up to GEMINI_MAX_RETRIES times with
# exponential back-off before the whole attempt is abandoned and the template
# fallback is used.  Keeps the Streamlit spinner from blocking forever.
GEMINI_REQUEST_TIMEOUT_MS: int = int(os.getenv("GEMINI_REQUEST_TIMEOUT_MS", "45000"))
GEMINI_MAX_RETRIES: int        = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

# ---------------------------------------------------------------------------
# Video rendering constants
# ---------------------------------------------------------------------------
VIDEO_FPS: int = 24
VIDEO_RESOLUTION: tuple[int, int] = (1280, 720)  # (width, height)
VIDEO_OUTPUT_DIR: str = "output"

# Scene durations (seconds).  With 4–8 photo slides the total will be
# approximately 20–40 s before transition overlap is subtracted.
TITLE_SCENE_DURATION: float  = 4.0   # opening title card
SLIDE_DURATION_SECONDS: float = 4.0  # each property photo slide
CONTACT_SCENE_DURATION: float = 5.0  # closing enquiry / contact card
TRANSITION_DURATION: float   = 0.5   # cross-fade between every scene

# ---------------------------------------------------------------------------
# Upload constraints
# ---------------------------------------------------------------------------
MIN_IMAGES: int = 4
MAX_IMAGES: int = 8
ALLOWED_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")

# ---------------------------------------------------------------------------
# Property types (used by the UI dropdown)
# ---------------------------------------------------------------------------
PROPERTY_TYPES: list[str] = [
    "Apartment",
    "Villa",
    "Independent House",
    "Plot / Land",
    "Commercial Office",
    "Penthouse",
    "Studio",
    "Row House",
]
