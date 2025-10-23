from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import os, time

# ---- Beállítások ----
FAVORITES_URL = "https://grok.com/imagine/favorites"
COOKIE_FILE   = "cookie.txt"           # egy sor: a "cookie:" header ÉRTÉKE (a "cookie:" szó nélkül)
DOWNLOAD_DIR  = "downloads"
HEADLESS      = False                   # ha kell, tedd True-ra
SCROLL_PAUSE_MS = 700                   # két görgetés között ennyi ms
MAX_IDLE_SCROLL_CYCLES = 3              # ennyi egymás utáni "nem nőtt az elemszám" után megállunk
UPSCALE_TIMEOUT_MS = 5 * 60 * 1000      # max várás az upscale -> Download megjelenésére

# ---- Szelektorok (XPath) ----
# Egy kártya konténer: a példád alapján ez a belső, "group/media-post-masonry-card" class-os div
CARD_XPATH = "//div[contains(@class,'group/media-post-masonry-card')]"
# Galéria bármely látható kártyája (a jelenlétét figyeljük a betöltéshez)
GALLERY_READY_XPATH = "(//div[@role='listitem'])[1]"
# Detail oldalon gombok (ha más a felirat, írd át)
UPSCALE_BTN = "//button[normalize-space()='Upscale' or contains(., 'Upscale')]"
DOWNLOAD_LINK = "//a[normalize-space()='Download' or contains(., 'Download')]"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def load_cookie_header(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        s = f.read().strip()
    if not s:
        raise ValueError("A cookie fájl üres.")
    return s

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
        })
    return cookies

def scroll_to_load_more(page):
    """Görget egy nagyot lefelé, kicsit vár."""
    page.mouse.wheel(0, 1800)
    page.wait_for_timeout(SCROLL_PAUSE_MS)

def load_gallery_incrementally(page, min_count=None):
    """
    Görget, amíg az elemszám nő. Ha min_count meg van adva, addig görget,
    míg el nem érjük ezt a darabszámot, vagy meg nem áll a növekedés.
    """
    idle = 0
    prev = 0
    while True:
        count = page.locator(f"xpath={CARD_XPATH}").count()
        if min_count is not None and count >= min_count:
            return count
        scroll_to_load_more(page)
        new_count = page.locator(f"xpath={CARD_XPATH}").count()
        if new_count == count:
            idle += 1
            if idle >= MAX_IDLE_SCROLL_CYCLES:
                return new_count
        else:
            idle = 0
        prev = new_count

def ensure_card_visible(page, index_zero_based: int):
    """
    Gondoskodik róla, hogy a kártya index szerint elérhető és látható legyen.
    Szükség esetén görget, amíg meg nem jelenik.
    """
    while True:
        count = page.locator(f"xpath={CARD_XPATH}").count()
        if count > index_zero_based:
            card = page.locator(f"xpath={CARD_XPATH}").nth(index_zero_based)
            try:
                card.scroll_into_view_if_needed(timeout=5000)
                # egy kis várakozás, hogy a videó fedődivjei stabilizálódjanak
                page.wait_for_timeout(200)
                return card
            except PWTimeout:
                pass
        # ha idáig jutunk, még nincs betöltve: görgessünk
        scroll_to_load_more(page)

def process_one_card(context, page, index_zero_based: int, download_dir: str):
    """Egy videó feldolgozása: megnyitás → Upscale → Download → vissza"""
    card = ensure_card_visible(page, index_zero_based)
    card.click()
    print(f"{index_zero_based+1}. kártya megnyitva.")

    try:
        # 1️⃣ Várjuk a hárompontos menüt
        page.wait_for_selector("button[aria-label='További lehetőségek']", timeout=15000)
        page.click("button[aria-label='További lehetőségek']")
        print("Megnyitottam a 'További lehetőségek' menüt...")

        # 2️⃣ Várjuk az 'Upscale video' menüpontot
        page.wait_for_selector("text=Upscale video", timeout=10000)
        page.click("text=Upscale video")
        print("Upscale elindítva...")

        # 3️⃣ Várjuk a letöltés linket (max. 5 perc)
        page.wait_for_selector("a:has-text('Download')", timeout=5 * 60 * 1000)
        print("Upscale kész, letöltés indul...")

        with page.expect_download() as dl_info:
            page.click("a:has-text('Download')")
        dl = dl_info.value
        filename = dl.suggested_filename or f"video_{index_zero_based+1}.mp4"
        dl.save_as(os.path.join(download_dir, filename))
        print(f"Letöltve: {filename}")

    except Exception as e:
        print(f"⚠️ Hiba a(z) {index_zero_based+1}. videónál: {e}")

    finally:
        # 4️⃣ Visszalépés a galériába
        try:
            page.go_back(timeout=15000)
            page.wait_for_selector("div[role='listitem']", timeout=15000)
        except:
            print("Visszalépés sikertelen (lehet modál), görgetés nélkül folytatom.")
        time.sleep(1)


def main():
    cookie_header = load_cookie_header(COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, domain="grok.com")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(accept_downloads=True)
        context.add_cookies(cookies)

        page = context.new_page()
        page.goto(FAVORITES_URL, wait_until="domcontentloaded")

        # Ellenőrzés: legyen legalább egy listitem
        try:
            page.wait_for_selector(f"xpath={GALLERY_READY_XPATH}", timeout=15000)
        except PWTimeout:
            print("❌ Nem látszik a galéria. Lehet, hogy a cookie lejárt / nem bejelentkezett állapot.")
            browser.close()
            return

        # Görgessünk, amíg már nem tölt be új kártyát
        total = load_gallery_incrementally(page)
        total = page.locator(f"xpath={CARD_XPATH}").count()
        print(f"Összes kártya betöltve: ~{total} (ha van még, görgetéskor nőhet).")

        # Végigmegyünk index szerint (minden kör elején biztosítjuk a láthatóságot)
        for i in range(total):
            print(f"\n--- {i+1}/{total} feldolgozása ---")
            process_one_card(context, page, i, DOWNLOAD_DIR)

        browser.close()
        print("\n🎉 Kész.")

if __name__ == "__main__":
    main()
