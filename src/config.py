import importlib
import importlib.util
import os
import sys

from .localization import t


def _resolve_load_dotenv():
    spec = importlib.util.find_spec("dotenv")
    if spec is None:

        def _noop():
            print(t("no_dotenv_warning"))

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
        print(t("invalid_int_config", key=key))
        return default


FAVORITES_URL = os.getenv("FAVORITES_URL", "https://grok.com/imagine/favorites")
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
)
COOKIE_FILE = os.getenv("COOKIE_FILE", "cookies.txt")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
HEADLESS = env_bool("HEADLESS", False)
LANGUAGE = os.getenv("LANGUAGE", "en")
SCROLL_PAUSE_MS = env_int("SCROLL_PAUSE_MS", 800)
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
MAX_SCROLLS_WITHOUT_NEW_CARDS = env_int("MAX_SCROLLS_WITHOUT_NEW_CARDS", 3)
SEARCH_SCROLL_UP_ATTEMPTS = env_int("SEARCH_SCROLL_UP_ATTEMPTS", 2)
SEARCH_SCROLL_DOWN_ATTEMPTS = env_int("SEARCH_SCROLL_DOWN_ATTEMPTS", 5)

# Playwright settings
BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome")
VIEWPORT_WIDTH = env_int("VIEWPORT_WIDTH", 1280)
VIEWPORT_HEIGHT = env_int("VIEWPORT_HEIGHT", 800)
BROWSER_LOCALE = os.getenv("BROWSER_LOCALE", "en-US")
BROWSER_TIMEZONE = os.getenv("BROWSER_TIMEZONE", "Europe/Paris")
BROWSER_COLOR_SCHEME = os.getenv("BROWSER_COLOR_SCHEME", "dark")

BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process,Translate,TranslateUI,TranslateSubFrames,LanguageDetection,RendererTranslate",
    "--disable-translate",
    "--accept-lang=hu-HU,hu,en-US,en,en-GB",
]

CONTEXT_HEADERS = {
    "Accept-Language": "hu-HU,hu;q=0.9",
    "Sec-CH-UA": '"Google Chrome";v="141", "Chromium";v="141", "Not=A?Brand";v="24"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}

INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['hu-HU', 'hu']});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
"""

# Media download options
SKIP_IMAGES = env_bool("SKIP_IMAGES", False)

# Selectors
CARDS_XPATH = "//div[contains(@class,'group/media-post-masonry-card')]"
GALLERY_LISTITEM_SELECTOR = "div[role='listitem']"
HD_BUTTON_SELECTOR = "button:has(div:text('HD'))"
VIDEO_IMAGE_TOGGLE_SELECTOR = "div[aria-label='Text alignment'][class*='flex'][class*='rounded-full']"

# Timeouts (in milliseconds)
CARD_VISIBILITY_TIMEOUT_MS = env_int("CARD_VISIBILITY_TIMEOUT_MS", 15000)
DOWNLOAD_BUTTON_TIMEOUT_MS = env_int("DOWNLOAD_BUTTON_TIMEOUT_MS", 60000)
BACK_BUTTON_TIMEOUT_MS = env_int("BACK_BUTTON_TIMEOUT_MS", 10000)
GALLERY_LOAD_TIMEOUT_MS = env_int("GALLERY_LOAD_TIMEOUT_MS", 15000)
MORE_OPTIONS_BUTTON_TIMEOUT_MS = env_int("MORE_OPTIONS_BUTTON_TIMEOUT_MS", 15000)

# HTTP timeouts (in seconds)
HTTP_REQUEST_TIMEOUT_SEC = env_int("HTTP_REQUEST_TIMEOUT_SEC", 60)

# Filename patterns
DEFAULT_FILENAME_PATTERN = "video_{index}.mp4"

# Asset routing configuration
ENABLE_ASSET_ROUTING = env_bool("ENABLE_ASSET_ROUTING", True)
ASSET_URL_PATTERN = os.getenv("ASSET_URL_PATTERN", "https://assets.grok.com/*")

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
