from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from dataclasses import dataclass
from typing import Optional, Tuple
import json
import os
import subprocess
import sys
import re
import requests
import random
import importlib


def _resolve_load_dotenv():
    spec = importlib.util.find_spec("dotenv")
    if spec is None:
        def _noop():
            print("⚠️  A python-dotenv csomag nincs telepítve, .env fájlok nem kerülnek betöltésre.")
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
UPSCALE_TIMEOUT_MS = env_int("UPSCALE_TIMEOUT_MS", 20 * 1000)  # 20 másodperc
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

# Terminál színezés egyszerű kényelmi eszközökkel (ha támogatott)
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
COLOR_GRAY = "\033[90m" if USE_COLOR else ""
COLOR_RESET = "\033[0m" if USE_COLOR else ""

_FFPROBE_AVAILABLE: Optional[bool] = None

# --- UI szövegkonstansok és segédfüggvények ---

MORE_OPTIONS_LABELS = ["További lehetőségek", "More options"]
DOWNLOAD_BUTTON_LABELS = ["Letöltés", "Download"]
BACK_BUTTON_LABELS = ["Vissza", "Back"]
UPSCALE_MENU_LABELS = ["Upscale video", "Videó felskálázása"]


def make_aria_selector(tag: str, labels):
    selectors = [f"{tag}[aria-label='{label}']" for label in labels]
    return ", ".join(selectors)


def build_menuitem_xpath(texts, disabled: bool):
    text_conditions = " or ".join([f"contains(normalize-space(.), '{text}')" for text in texts])
    disabled_clause = "@aria-disabled='true'" if disabled else "not(@aria-disabled)"
    return f"//div[@role='menuitem' and ({text_conditions}) and {disabled_clause}]"


MORE_OPTIONS_BUTTON_SELECTOR = make_aria_selector("button", MORE_OPTIONS_LABELS)
DOWNLOAD_BUTTON_SELECTOR = make_aria_selector("button", DOWNLOAD_BUTTON_LABELS)
BACK_BUTTON_SELECTOR = make_aria_selector("button", BACK_BUTTON_LABELS)
UPSCALE_MENU_DISABLED_XPATH = build_menuitem_xpath(UPSCALE_MENU_LABELS, disabled=True)
UPSCALE_MENU_ACTIVE_XPATH = build_menuitem_xpath(UPSCALE_MENU_LABELS, disabled=False)


# --- Segédfüggvények ---


def load_cookie_header(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        data = f.read().strip()
    if not data:
        raise ValueError("A cookie fájl üres!")
    return data


def cookie_header_to_list(header: str, domain: str):
    cookies = []
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": domain,
            "path": "/",
            "secure": True,
            "sameSite": "None"
        })
    return cookies


def wait_with_jitter(page, base_ms: int):
    page.wait_for_timeout(base_ms + random.randint(0, WAIT_JITTER_MS))


def scroll_to_load_more(page):
    print("⬇️  Görgetés...")
    page.mouse.wheel(0, MOUSE_SCROLL + random.randint(0, MOUSE_SCROLL_JITTER_MS))
    wait_with_jitter(page, SCROLL_PAUSE_MS)


def click_safe_area(page):
    viewport = page.viewport_size or {"width": 1280, "height": 800}
    x = int(min(max(viewport["width"] * 0.6, 200), viewport["width"] - 80))
    y = int(min(max(viewport["height"] * 0.2, 120), viewport["height"] - 120))
    page.mouse.click(x, y)


def extract_video_source(page) -> Optional[str]:
    selectors = [
        "video#hd-video[src]",
        "video#sd-video[src]",
        "video[src]",
    ]
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=3000)
        except PWTimeout:
            continue

        locator = page.locator(selector)
        if locator.count() == 0:
            continue

        try:
            src = locator.first.get_attribute("src")
        except Exception:
            src = None

        if src:
            return src
    return None


@dataclass
class MediaCheckResult:
    image_path: str
    image_exists: bool
    video_path: str
    video_exists: bool
    video_width: Optional[int]


def probe_video_width(path: str) -> Optional[int]:
    global _FFPROBE_AVAILABLE

    if _FFPROBE_AVAILABLE is False:
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        if _FFPROBE_AVAILABLE is not False:
            _FFPROBE_AVAILABLE = False
            print("⚠️  ffprobe nem található, a videók felbontását nem tudom ellenőrizni – újra feldolgozom őket.")
        return None
    except subprocess.CalledProcessError:
        return None
    else:
        _FFPROBE_AVAILABLE = True

    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        if streams:
            width_value = streams[0].get("width")
            if width_value is not None:
                return int(width_value)
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    return None


def analyze_existing_media(image_filename: str) -> MediaCheckResult:
    name_without_ext, _ = os.path.splitext(image_filename)
    image_path = os.path.join(DOWNLOAD_DIR, f"grok-image-{name_without_ext}.png")
    video_path = os.path.join(DOWNLOAD_DIR, f"grok-video-{name_without_ext}.mp4")

    image_exists = os.path.exists(image_path)
    video_exists = os.path.exists(video_path)
    video_width = probe_video_width(video_path) if video_exists else None

    return MediaCheckResult(
        image_path=image_path,
        image_exists=image_exists,
        video_path=video_path,
        video_exists=video_exists,
        video_width=video_width,
    )


def decide_media_action(image_filename: str) -> Tuple[str, MediaCheckResult]:
    info = analyze_existing_media(image_filename)

    if info.image_exists and not info.video_exists:
        return "skip_image", info

    if info.video_exists:
        if info.video_width is None:
            return "process", info
        if info.video_width >= UPSCALE_VIDEO_WIDTH:
            return "skip_video", info
        return "process", info

    return "process", info


def get_filename_from_url(url: str, index: int):
    """Próbáljuk az URL-ből kinyerni a Grok video ID-t, fallback az index."""
    m = re.search(r"([a-f0-9-]{36})", url)
    return f"{m.group(1) if m else f'video_{index + 1}'} .mp4"


def get_card_identifier(card):
    try:
        identifier = card.evaluate('el => el.querySelector("img")?.src || null')
        if identifier:
            identifier = str(identifier)
            slash_index = identifier.rfind("/")
            if slash_index != -1 and slash_index + 1 < len(identifier):
                name = identifier[slash_index + 1:]
                question_index = name.find("?")
                if question_index != -1:
                    name = name[:question_index]
                if name:
                    return name
            return identifier
    except Exception:
        print("❌ Hiba a videó azonosító kinyerésekor.")
        pass
    return "No ID"


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    concat_segments = []
    for index, segment in enumerate(parts):
        if segment:
            concat_segments.append(f"'{segment}'")
        if index != len(parts) - 1:
            concat_segments.append("\"'\"")
    return "concat(" + ", ".join(concat_segments) + ")"


def find_card_by_identifier(page, target_identifier: str):
    """Keressük meg a kártyát közvetlenül az img src alapján, függetlenül az aktuális DOM sorrendtől."""
    literal = xpath_literal(target_identifier)
    img_locator = page.locator(
        f"//div[contains(@class,'group/media-post-masonry-card')]//img[contains(@src, {literal})]"
    )
    if img_locator.count() == 0:
        return None
    return img_locator.first.locator("xpath=ancestor::div[contains(@class,'group/media-post-masonry-card')]").first

# --- Fő feldolgozó ---


def process_one_card(context, page, card, index: int, identifier: str, upscale_failures: list, download_failures: list):
    print(f"\n🎬 {index + 1}. ({identifier}) videó feldolgozása...")

    def record_failure(reason: str):
        print(f"❌ Letöltési hiba: {reason}")
        download_failures.append((identifier, reason))

    for attempt in range(2):
        try:
            card.scroll_into_view_if_needed()
            card.wait_for(state="visible", timeout=15000)
            wait_with_jitter(page, WAIT_AFTER_CARD_SCROLL_MS)
            card.click()
            print("🖱️  Megnyitva...")
            break
        except PWTimeout:
            if attempt == 0:
                print("♻️  A kártya eltűnt, újrakeresem...")
                refreshed = find_card_by_identifier(page, identifier)
                if refreshed is None:
                    record_failure("A kártya nem található a kattintáshoz")
                    return
                card = refreshed
                continue
            record_failure("A kártyára kattintás időtúllépett")
            return

    try:
        # 1️⃣ Menü megnyitása
        page.wait_for_selector(MORE_OPTIONS_BUTTON_SELECTOR, timeout=15000)
        page.locator(MORE_OPTIONS_BUTTON_SELECTOR).first.click()
        print("📂 Menü megnyitva...")

        # 2️⃣ Upscale állapot ellenőrzés
        disabled = page.locator(UPSCALE_MENU_DISABLED_XPATH)
        active = page.locator(UPSCALE_MENU_ACTIVE_XPATH)
        wait_with_jitter(page, WAIT_AFTER_CARD_SCROLL_MS)

        if disabled.count() > 0:
            print("🟢 Már upscale-elve van, kihagyom az upscale lépést.")
            click_safe_area(page)
        else:
            print("🕐 Upscale indítása...")
            active.first.click()
            wait_with_jitter(page, WAIT_AFTER_MENU_INTERACTION_MS)
            click_safe_area(page)
            try:
                # várjuk a HD ikon megjelenését
                page.wait_for_selector("button:has(div:text('HD'))", timeout=UPSCALE_TIMEOUT_MS)
                print("✅ Upscale kész.")
            except PWTimeout:
                print("⚠️  Upscale időtúllépés – letöltés upscale nélkül.")
                upscale_failures.append(identifier)

        # 3️⃣ Menü bezárása
        wait_with_jitter(page, WAIT_AFTER_MENU_INTERACTION_MS)

        # 4️⃣ Letöltés
        dl_button = page.locator(DOWNLOAD_BUTTON_SELECTOR)
        if dl_button.count() == 0:
            record_failure("Nem találtam Letöltés gombot.")
            return
        dl_button.first.wait_for(state="visible", timeout=60000)

        with page.expect_download() as dl_info:
            dl_button.first.click()
        download = dl_info.value

        filename = download.suggested_filename or f"video_{index + 1}.mp4"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        # ha már létezik, töröljük hogy a friss példány felülírhassa
        if os.path.exists(filepath):
            print(f"🟡 Már létezik ({filename}), felülírom.")
            try:
                os.remove(filepath)
            except OSError as remove_err:
                record_failure(f"Nem tudtam törölni a régi fájlt: {remove_err}")
                return

        download.save_as(filepath)

        # 0-bájtos letöltés detektálás
        if os.path.getsize(filepath) == 0:
            print("⚠️  0 bájtos fájl — törlöm és megpróbálom a megnyitott kártyából letölteni...")
            try:
                os.remove(filepath)
            except OSError as remove_err:
                record_failure(f"Nem tudtam törölni a 0 bájtos fájlt: {remove_err}")
                return

            fallback_url = extract_video_source(page)
            if not fallback_url:
                record_failure("Nem találtam videó URL-t a kártya DOM-jában")
                return

            print(f"🔁 Alternatív letöltés: {fallback_url}")

            headers = {
                "user-agent": USER_AGENT,
                "accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                "referer": FAVORITES_URL,
            }

            try:
                r = requests.get(fallback_url, stream=True, headers=headers, timeout=60)
            except requests.RequestException as req_err:
                record_failure(f"Alternatív letöltés HTTP hiba:\n{COLOR_GRAY}{req_err}{COLOR_RESET}")
                return

            if not r.ok:
                record_failure(f"Alternatív letöltés sikertelen: HTTP {r.status_code}")
                return

            with open(filepath, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    f.write(chunk)

            alt_size = os.path.getsize(filepath)
            if alt_size == 0:
                record_failure("Alternatív letöltés is 0 bájtos maradt")
                return
            print(f"📥 Letöltve alternatív forrásból: {filename} ({alt_size} bájt)")
        else:
            print(f"📥 Letöltve: {filename}")

    except Exception as e:
        record_failure(f"Hiba a(z) {index + 1}. videónál:\n{COLOR_GRAY}{e}{COLOR_RESET}")

    finally:
        # 5️⃣ Visszalépés
        try:
            back_button = page.locator(BACK_BUTTON_SELECTOR).first
            back_button.wait_for(state="visible", timeout=10000)
            wait_with_jitter(page, WAIT_AFTER_BACK_BUTTON_MS)
            back_button.click()
            page.wait_for_selector("div[role='listitem']", timeout=15000)
            print("↩️  Visszatérés a galériába.")
        except:
            print("⚠️  Nem sikerült visszalépni, de folytatom.")
        wait_with_jitter(page, WAIT_AFTER_BACK_BUTTON_MS)


def main():
    cookie_header = load_cookie_header(COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, ".grok.com")

    with sync_playwright() as p:
        # Realistic user-agent (Chrome Win10)
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process,Translate,TranslateUI,TranslateSubFrames,LanguageDetection,RendererTranslate',
            '--disable-translate',
            '--accept-lang=hu-HU,hu,en-US,en,en-GB',
        ]
        # context = p.chromium.launch_persistent_context(
        #     user_data_dir="user-data",
        #     args=launch_args,
        #     locale="en-US"
        # )
        browser = p.chromium.launch(channel="chrome", headless=HEADLESS, args=launch_args)
        context = browser.new_context(
            accept_downloads=True,
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="Europe/Budapest",
            color_scheme="dark",
            extra_http_headers={
                "Accept-Language": "hu-HU,hu;q=0.9",
                "Sec-CH-UA": '"Google Chrome";v="141", "Chromium";v="141", "Not=A?Brand";v="24"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
            },
        )
        context.add_cookies(cookies)
        page = context.new_page()

        def asset_header_rewrite(route, request):
            headers = dict(request.headers)
            headers.update(ASSET_BASE_HEADERS)
            headers.setdefault("user-agent", USER_AGENT)
            route.continue_(headers=headers)

        page.route("https://assets.grok.com/*", asset_header_rewrite)

        # Remove navigator.webdriver property
        page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = window.chrome || { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['hu-HU', 'hu']});
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
        """
        )

        print("🌐 Galéria megnyitása...")
        response = page.goto(FAVORITES_URL, wait_until="domcontentloaded")

        if response and response.status == 403:
            print("❌ 403 Forbidden — valószínűleg a cookie érvénytelen vagy a böngésző fingerprint blokkolt.")
            print("ℹ️ Próbáld új cookie fájl generálását ugyanazzal a böngészővel és user-agenttel, ahonnan a cookie származik.")
            return

        wait_with_jitter(page, INITIAL_PAGE_WAIT_MS)
        try:
            page.wait_for_selector("div[role='listitem']", timeout=15000)
        except PWTimeout:
            print("❌ Nem sikerült betölteni a galériát – ellenőrizd a cookie fájlt.")
            return

        cards_locator = page.locator("//div[contains(@class,'group/media-post-masonry-card')]")
        processed_ids = set()
        pending_queue = []
        pending_set = set()
        processed_count = 0
        idle_cycles = 0
        upscale_failures = []
        download_failures = []

        try:
            while True:
                card_count = cards_locator.count()
                new_cards_added = False

                for idx in range(card_count):
                    card = cards_locator.nth(idx)
                    identifier = get_card_identifier(card)
                    if not identifier or identifier == "No ID":
                        continue
                    if identifier in processed_ids or identifier in pending_set:
                        continue

                    media_info = analyze_existing_media(identifier)

                    if media_info.image_exists:
                        print(f"⏭️  Már lementett kép: {media_info.image_path}")
                        processed_ids.add(identifier)
                        continue
                    elif media_info.video_exists:
                        if media_info.video_width is not None and media_info.video_width >= UPSCALE_VIDEO_WIDTH:
                            print(f"⏭️  Már létező videó ({media_info.video_width}px): {media_info.video_path}")
                            processed_ids.add(identifier)
                            continue
                        else:
                            width_txt = f"{media_info.video_width}px" if media_info.video_width else "ismeretlen"
                            print(f"♻️  Létező, de nem megfelelő felbontású videó ({width_txt}): {media_info.video_path}")

                    pending_queue.append(identifier)
                    pending_set.add(identifier)
                    new_cards_added = True

                if new_cards_added:
                    idle_cycles = 0

                if not pending_queue:
                    idle_cycles += 1
                    if idle_cycles == 1:
                        print("🌀 Nincs feldolgozandó kártya, görgetek tovább...")
                    elif idle_cycles % MAX_IDLE_SCROLL_CYCLES == 0:
                        print(f"🌀 További görgetés ({idle_cycles} próbálkozás) ...")

                    wait_with_jitter(page, WAIT_IDLE_LOOP_MS)
                    scroll_to_load_more(page)
                    continue

                print(f"🔢 Hátralévő megtalált videók ({len(pending_queue)}): {COLOR_GRAY}{pending_queue}{COLOR_RESET}")

                identifier = pending_queue.pop(0)
                pending_set.discard(identifier)

                card = find_card_by_identifier(page, identifier)

                if card is None:
                    print("🔄 Kártya nincs a DOM-ban, görgetés lefelé...")
                    retries = 0
                    found_card = None
                    while retries < MAX_IDLE_SCROLL_CYCLES and found_card is None:
                        scroll_to_load_more(page)
                        found_card = find_card_by_identifier(page, identifier)
                        retries += 1
                    if found_card is None:
                        print(f"⚠️  {identifier} kártya nem található, kihagyás.")
                        processed_ids.add(identifier)
                        idle_cycles = 0
                        continue
                    card = found_card

                process_one_card(
                    context,
                    page,
                    card,
                    processed_count,
                    identifier,
                    upscale_failures,
                    download_failures,
                )
                processed_ids.add(identifier)
                processed_count += 1
                idle_cycles = 0

            print("\n🎉 Kész – minden videó feldolgozva.")
        except Exception as e:
            print(f"❌ Folyamat megszakadt:\n\n{COLOR_GRAY}{e}{COLOR_RESET}")
            err_text = str(e).lower()
            transient_browser_errors = (
                "target closed",
                "page closed",
                "browser has been closed",
            )
            if not any(token in err_text for token in transient_browser_errors):
                raise
        finally:
            if upscale_failures:
                print("\n⚠️  Az alábbi videók upscale nélkül kerültek letöltésre:")
                for failed in upscale_failures:
                    print(f"   • {failed}")
            else:
                print("\n✅ Minden videó sikeresen upscale-lve lett a letöltés előtt.")

            if download_failures:
                print("\n❗ Letöltési hibák listája:")
                for ident, reason in download_failures:
                    print(f"   • {ident}: {reason}")
            else:
                print("\n✅ Nem történt letöltési hiba.")
            try:
                # context.close()
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
