from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import os, time, re, requests
import random

FAVORITES_URL = "https://grok.com/imagine/favorites"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
COOKIE_FILE = "cookies.txt"
DOWNLOAD_DIR = "downloads"
HEADLESS = False
SCROLL_PAUSE_MS = 700
MAX_IDLE_SCROLL_CYCLES = 3
UPSCALE_TIMEOUT_MS = 5 * 60 * 1000  # 5 perc
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

def scroll_to_load_more(page):
    page.mouse.wheel(0, 2000)
    page.wait_for_timeout(random.randint(100, 400) + SCROLL_PAUSE_MS)

def ensure_cards_loaded(page):
    idle = 0
    prev = 0
    while True:
        count = page.locator("//div[contains(@class,'group/media-post-masonry-card')]").count()
        if count == prev:
            idle += 1
            if idle >= MAX_IDLE_SCROLL_CYCLES:
                return
        else:
            idle = 0
        prev = count
        scroll_to_load_more(page)

def get_filename_from_url(url: str, index: int):
    """Próbáljuk az URL-ből kinyerni a Grok video ID-t, fallback az index."""
    m = re.search(r"([a-f0-9-]{36})", url)
    return f"{m.group(1) if m else f'video_{index+1}'} .mp4"

# --- Fő feldolgozó ---

def process_one_card(context, page, card, index: int):
    print(f"\n🎬 {index+1}. videó feldolgozása...")
    card.scroll_into_view_if_needed()
    page.wait_for_timeout(random.randint(500, 800))
    card.click()
    print("🖱️ Megnyitva...")

    try:
        # 1️⃣ Menü megnyitása
        page.wait_for_selector("button[aria-label='További lehetőségek']", timeout=15000)
        page.click("button[aria-label='További lehetőségek']")
        print("📂 Menü megnyitva...")

        # 2️⃣ Upscale állapot ellenőrzés
        disabled = page.locator("//div[@role='menuitem' and contains(., 'Upscale video') and @aria-disabled='true']")
        active = page.locator("//div[@role='menuitem' and contains(., 'Upscale video') and not(@aria-disabled)]")

        if disabled.count() > 0:
            print("🟢 Már upscale-elve van, kihagyom az upscale lépést.")
            page.wait_for_timeout(random.randint(300, 500))
            page.mouse.click(200, 100)
        else:
            print("🕐 Upscale indítása...")
            active.first.click()
            page.wait_for_timeout(random.randint(300, 500))
            page.mouse.click(200, 100)
            # várjuk a HD ikon megjelenését
            page.wait_for_selector("button:has(div:text('HD'))", timeout=UPSCALE_TIMEOUT_MS)
            print("✅ Upscale kész.")

        # 3️⃣ Menü bezárása
        page.wait_for_timeout(random.randint(100, 300))

        # 4️⃣ Letöltés
        page.wait_for_selector("button[aria-label='Letöltés']", timeout=60000)
        dl_button = page.locator("button[aria-label='Letöltés']")
        if not dl_button:
            print("❌ Nem találtam Letöltés gombot.")
            return

        with page.expect_download() as dl_info:
            dl_button.click()
        download = dl_info.value

        filename = download.suggested_filename or f"video_{index+1}.mp4"
        filepath = os.path.join(DOWNLOAD_DIR, filename)

        # ha már létezik
        if os.path.exists(filepath):
            print(f"🟡 Már létezik ({filename}), kihagyom.")
            return

        download.save_as(filepath)

        # 0-bájtos letöltés detektálás
        if os.path.getsize(filepath) == 0:
            print("⚠️ 0 bájtos fájl — megpróbálom közvetlen URL-ből letölteni...")
            url = download.url
            if url:
                page_cookies = context.cookies()
                cookie_jar = {c['name']: c['value'] for c in page_cookies if "grok.com" in c['domain']}
                headers = ASSET_BASE_HEADERS.copy()
                headers.update({
                    "user-agent": USER_AGENT,
                })
                try:
                    r = requests.get(url, stream=True, headers=headers, cookies=cookie_jar, timeout=60)
                except requests.RequestException as req_err:
                    print(f"❌ HTTP hiba: {req_err}")
                    return
                if r.ok:
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(1024 * 1024):
                            f.write(chunk)
                    print(f"📥 Letöltve: {filename} ({os.path.getsize(filepath)} bájt)")
                else:
                    print("❌ Közvetlen letöltés sem sikerült.")
            else:
                print("❌ Nem ismert az URL.")
        else:
            print(f"📥 Letöltve: {filename}")

    except Exception as e:
        print(f"❌ Hiba a(z) {index+1}. videónál: {e}")

    finally:
        # 5️⃣ Visszalépés
        try:
            page.click("button[aria-label='Vissza']")
            page.wait_for_selector("div[role='listitem']", timeout=15000)
            print("↩️ Visszatérés a galériába.")
        except:
            print("⚠️ Nem sikerült visszalépni, de folytatom.")
        time.sleep(1)


def main():
    cookie_header = load_cookie_header(COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, ".grok.com")

    with sync_playwright() as p:
        # Realistic user-agent (Chrome Win10)
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--disable-features=TranslateUI',
        ]
        try:
            browser = p.chromium.launch(channel="chrome", headless=HEADLESS, args=launch_args)
        except Exception:
            try:
                browser = p.chromium.launch(channel="msedge", headless=HEADLESS, args=launch_args)
            except Exception:
                browser = p.chromium.launch(headless=HEADLESS, args=launch_args)
        context = browser.new_context(
            accept_downloads=True,
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="hu-HU",
            timezone_id="Europe/Budapest",
            color_scheme="dark",
            extra_http_headers={
                "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
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
            Object.defineProperty(navigator, 'languages', {get: () => ['hu-HU', 'hu', 'en-US', 'en']});
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

        page.wait_for_timeout(12000)
        try:
            page.wait_for_selector("div[role='listitem']", timeout=15000)
        except PWTimeout:
            print("❌ Nem sikerült betölteni a galériát – ellenőrizd a cookie fájlt.")
            return

        print("🔽 Görgetés a teljes lista betöltéséhez...")
        ensure_cards_loaded(page)
        cards = page.locator("//div[contains(@class,'group/media-post-masonry-card')]").all()
        print(f"📸 Összesen {len(cards)} videó található.")

        for i in range(len(cards)):
            # mindig újra lekérdezzük, hogy az index biztos jó legyen
            cards = page.locator("//div[contains(@class,'group/media-post-masonry-card')]").all()
            if i >= len(cards):
                break
            process_one_card(context, page, cards[i], i)

        print("\n🎉 Kész – minden videó feldolgozva.")
        browser.close()

if __name__ == "__main__":
    main()
