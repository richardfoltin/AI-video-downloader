from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import os, time

FAVORITES_URL = "https://grok.com/imagine/favorites"
COOKIE_FILE = "cookie.txt"
DOWNLOAD_DIR = "downloads"
HEADLESS = False
SCROLL_PAUSE_MS = 700
MAX_IDLE_SCROLL_CYCLES = 3
UPSCALE_TIMEOUT_MS = 5 * 60 * 1000  # 5 perc

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

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
            "secure": True
        })
    return cookies

def scroll_to_load_more(page):
    page.mouse.wheel(0, 2000)
    page.wait_for_timeout(SCROLL_PAUSE_MS)

def ensure_card_visible(page, index_zero_based: int):
    """Görget, amíg az adott indexű kártya betöltődik."""
    while True:
        count = page.locator("//div[contains(@class,'group/media-post-masonry-card')]").count()
        if count > index_zero_based:
            card = page.locator("//div[contains(@class,'group/media-post-masonry-card')]").nth(index_zero_based)
            card.scroll_into_view_if_needed(timeout=5000)
            page.wait_for_timeout(200)
            return card
        scroll_to_load_more(page)

def process_one_card(page, index: int, download_dir: str):
    """Egy videó feldolgozása (upscale, letöltés, vissza)."""
    print(f"\n--- {index+1}. videó ---")

    card = ensure_card_visible(page, index)
    card.click()
    print("Kártya megnyitva...")

    try:
        # 1️⃣ További lehetőségek (⋯) megnyitása
        page.wait_for_selector("button[aria-label='További lehetőségek']", timeout=15000)
        page.click("button[aria-label='További lehetőségek']")
        print("Menü megnyitva...")

        # 2️⃣ Upscale menüpont keresése
        try:
            disabled_upscale = page.locator("//div[@role='menuitem' and contains(., 'Upscale video') and @aria-disabled='true']")
            active_upscale = page.locator("//div[@role='menuitem' and contains(., 'Upscale video') and not(@aria-disabled)]")

            if disabled_upscale.count() > 0:
                print("Ez a videó már upscale-elve van – kihagyom az upscale-t.")
            else:
                print("Upscale elindítva...")
                active_upscale.first.click()

                # 3️⃣ Várjuk a HD ikon (kész upscale) megjelenését
                page.wait_for_selector("button:has(div:text('HD'))", timeout=UPSCALE_TIMEOUT_MS)
                print("Upscale kész.")

        except PWTimeout:
            print("Upscale menüpont nem található vagy időtúllépés.")

        # 4️⃣ Menü bezárása (kattintás valahova máshova)
        page.mouse.click(10, 10)
        page.wait_for_timeout(500)

        # 5️⃣ Letöltés gomb megvárása
        page.wait_for_selector("button[aria-label='Letöltés']", timeout=60000)
        with page.expect_download() as dl_info:
            page.click("button[aria-label='Letöltés']")
        dl = dl_info.value
        filename = dl.suggested_filename or f"video_{index+1}.mp4"
        dl.save_as(os.path.join(download_dir, filename))
        print(f"Letöltve: {filename}")

    except Exception as e:
        print(f"⚠️ Hiba a(z) {index+1}. videónál: {e}")

    finally:
        # 6️⃣ Vissza a galériába
        try:
            page.click("button[aria-label='Vissza']")
            page.wait_for_selector("div[role='listitem']", timeout=15000)
            print("Visszatérés a galériába.")
        except:
            print("Nem sikerült visszalépni, folytatom a következővel.")
        time.sleep(1)


def main():
    cookie_header = load_cookie_header(COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, "grok.com")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(accept_downloads=True)
        context.add_cookies(cookies)
        page = context.new_page()

        print("Galéria megnyitása...")
        page.goto(FAVORITES_URL, wait_until="domcontentloaded")

        try:
            page.wait_for_selector("div[role='listitem']", timeout=15000)
        except PWTimeout:
            print("❌ Nem sikerült betölteni a galériát – ellenőrizd a cookie fájlt.")
            return

        total = 0
        idle = 0
        while True:
            count = page.locator("//div[contains(@class,'group/media-post-masonry-card')]").count()
            if count == total:
                idle += 1
                if idle >= MAX_IDLE_SCROLL_CYCLES:
                    break
            else:
                total = count
                idle = 0
            scroll_to_load_more(page)

        print(f"Összes videó betöltve: {total}")

        for i in range(total):
            process_one_card(page, i, DOWNLOAD_DIR)

        browser.close()
        print("\n🎉 Kész – minden videó feldolgozva.")

if __name__ == "__main__":
    main()
