"""Configuration and constants."""

from pathlib import Path

# Project directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
COOKIES_DIR = PROJECT_ROOT / "cookies"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Default configuration
DEFAULT_TIMEOUT = 30000
DEFAULT_HEADLESS = False
