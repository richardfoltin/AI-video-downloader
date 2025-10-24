import importlib
import importlib.util
import os
import sys


def _resolve_load_dotenv():
    spec = importlib.util.find_spec("dotenv")
    if spec is None:
        def _noop():
            print("⚠️  A python-dotenv csomag nincs telepítve, .env fájl nem kerül betöltésre.")
        return _noop
    module = importlib.import_module("dotenv")
    return getattr(module, "load_dotenv", lambda: None)


load_dotenv = _resolve_load_dotenv()
load_dotenv()


def env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"⚠️  Érvénytelen egész szám a(z) {key} változóban, az alapértelmezett értéket használom.")
        return default


FAVORITES_URL = os.getenv("FAVORITES_URL", "https://grok.com/imagine/favorites")
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
)
COOKIE_FILE = os.getenv("COOKIE_FILE", "cookies.txt")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
HEADLESS = env_bool("HEADLESS", False)
SCROLL_PAUSE_MS = env_int("SCROLL_PAUSE_MS", 800)
MAX_IDLE_SCROLL_CYCLES = env_int("MAX_IDLE_SCROLL_CYCLES", 10)
UPSCALE_TIMEOUT_MS = env_int("UPSCALE_TIMEOUT_MS", 20 * 1000)
UPSCALE_VIDEO_WIDTH = env_int("UPSCALE_VIDEO_WIDTH", 928)
MOUSE_SCROLL = env_int("MOUSE_SCROLL", 400)
MOUSE_SCROLL_JITTER_MS = env_int("MOUSE_SCROLL_JITTER_MS", 100)
WAIT_JITTER_MS = env_int("WAIT_JITTER_MS", 200)
WAIT_AFTER_CARD_SCROLL_MS = env_int("WAIT_AFTER_CARD_SCROLL_MS", 600)
WAIT_AFTER_MENU_INTERACTION_MS = env_int("WAIT_AFTER_MENU_INTERACTION_MS", 400)
WAIT_AFTER_BACK_BUTTON_MS = env_int("WAIT_AFTER_BACK_BUTTON_MS", 400)
WAIT_IDLE_LOOP_MS = env_int("WAIT_IDLE_LOOP_MS", 300)
INITIAL_PAGE_WAIT_MS = env_int("INITIAL_PAGE_WAIT_MS", 5000)

ASSET_BASE_HEADERS = {
    "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "accept-language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    "priority": "i",
    "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "image",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "same-site",
    "referer": "https://grok.com/",
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
COLOR_GRAY = "\033[90m" if USE_COLOR else ""
COLOR_RESET = "\033[0m" if USE_COLOR else ""

MORE_OPTIONS_LABELS = ["További lehetőségek", "More options"]
DOWNLOAD_BUTTON_LABELS = ["Letöltés", "Download"]
BACK_BUTTON_LABELS = ["Vissza", "Back"]
UPSCALE_MENU_LABELS = ["Upscale video", "Videó felskálázása"]
