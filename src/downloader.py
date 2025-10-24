from __future__ import annotations

import os
from typing import List

import requests
from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from . import config
from .cookies import cookie_header_to_list, load_cookie_header
from .media import decide_media_action
from .playwright_utils import (
    BACK_BUTTON_SELECTOR,
    DOWNLOAD_BUTTON_SELECTOR,
    MORE_OPTIONS_BUTTON_SELECTOR,
    UPSCALE_MENU_ACTIVE_XPATH,
    UPSCALE_MENU_DISABLED_XPATH,
    click_safe_area,
    extract_video_source,
    find_card_by_identifier,
    get_card_identifier,
    scroll_to_load_more,
    wait_with_jitter,
)


def process_one_card(context, page, card, index: int, identifier: str, upscale_failures: List[str], download_failures: List[tuple]):
    print(f"\n🎬 {index + 1}. ({identifier}) videó feldolgozása...")

    def record_failure(reason: str):
        print(f"❌ Letöltési hiba: {reason}")
        download_failures.append((identifier, reason))

    for attempt in range(2):
        try:
            card.scroll_into_view_if_needed()
            card.wait_for(state="visible", timeout=15000)
            wait_with_jitter(page, config.WAIT_AFTER_CARD_SCROLL_MS)
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
        page.wait_for_selector(MORE_OPTIONS_BUTTON_SELECTOR, timeout=15000)
        page.locator(MORE_OPTIONS_BUTTON_SELECTOR).first.click()
        print("📂 Menü megnyitva...")

        disabled = page.locator(UPSCALE_MENU_DISABLED_XPATH)
        active = page.locator(UPSCALE_MENU_ACTIVE_XPATH)
        wait_with_jitter(page, config.WAIT_AFTER_CARD_SCROLL_MS)

        if disabled.count() > 0:
            print("🟢 Már upscale-elve van, kihagyom az upscale lépést.")
            click_safe_area(page)
        else:
            print("🕐 Upscale indítása...")
            active.first.click()
            wait_with_jitter(page, config.WAIT_AFTER_MENU_INTERACTION_MS)
            click_safe_area(page)
            try:
                page.wait_for_selector("button:has(div:text('HD'))", timeout=config.UPSCALE_TIMEOUT_MS)
                print("✅ Upscale kész.")
            except PWTimeout:
                print("⚠️  Upscale időtúllépés – letöltés upscale nélkül.")
                upscale_failures.append(identifier)

        wait_with_jitter(page, config.WAIT_AFTER_MENU_INTERACTION_MS)

        dl_button = page.locator(DOWNLOAD_BUTTON_SELECTOR)
        if dl_button.count() == 0:
            record_failure("Nem találtam Letöltés gombot.")
            return
        dl_button.first.wait_for(state="visible", timeout=60000)

        with page.expect_download() as dl_info:
            dl_button.first.click()
        download = dl_info.value

        filename = download.suggested_filename or f"video_{index + 1}.mp4"
        filepath = os.path.join(config.DOWNLOAD_DIR, filename)

        if os.path.exists(filepath):
            print(f"🟡 Már létezik ({filename}), felülírom.")
            try:
                os.remove(filepath)
            except OSError as remove_err:
                record_failure(f"Nem tudtam törölni a régi fájlt: {remove_err}")
                return

        download.save_as(filepath)

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
                "user-agent": config.USER_AGENT,
                "accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                "referer": config.FAVORITES_URL,
            }

            try:
                response = requests.get(fallback_url, stream=True, headers=headers, timeout=60)
            except requests.RequestException as req_err:
                record_failure(f"Alternatív letöltés HTTP hiba:\n{config.COLOR_GRAY}{req_err}{config.COLOR_RESET}")
                return

            if not response.ok:
                record_failure(f"Alternatív letöltés sikertelen: HTTP {response.status_code}")
                return

            with open(filepath, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)

            alt_size = os.path.getsize(filepath)
            if alt_size == 0:
                record_failure("Alternatív letöltés is 0 bájtos maradt")
                return
            print(f"📥 Letöltve alternatív forrásból: {filename} ({alt_size} bájt)")
        else:
            print(f"📥 Letöltve: {filename}")

    except Exception as error:
        record_failure(f"Hiba a(z) {index + 1}. videónál:\n{config.COLOR_GRAY}{error}{config.COLOR_RESET}")

    finally:
        try:
            back_button = page.locator(BACK_BUTTON_SELECTOR).first
            back_button.wait_for(state="visible", timeout=10000)
            wait_with_jitter(page, config.WAIT_AFTER_BACK_BUTTON_MS)
            back_button.click()
            page.wait_for_selector("div[role='listitem']", timeout=15000)
            print("↩️  Visszatérés a galériába.")
        except Exception:
            print("⚠️  Nem sikerült visszalépni, de folytatom.")
        wait_with_jitter(page, config.WAIT_AFTER_BACK_BUTTON_MS)


def run():
    cookie_header = load_cookie_header(config.COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, ".grok.com")

    with sync_playwright() as playwright:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process,Translate,TranslateUI,TranslateSubFrames,LanguageDetection,RendererTranslate",
            "--disable-translate",
            "--accept-lang=hu-HU,hu,en-US,en,en-GB",
        ]
        browser = playwright.chromium.launch(channel="chrome", headless=config.HEADLESS, args=launch_args)
        context = browser.new_context(
            accept_downloads=True,
            user_agent=config.USER_AGENT,
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
            headers.update(config.ASSET_BASE_HEADERS)
            headers.setdefault("user-agent", config.USER_AGENT)
            route.continue_(headers=headers)

        page.route("https://assets.grok.com/*", asset_header_rewrite)

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
        response = page.goto(config.FAVORITES_URL, wait_until="domcontentloaded")

        if response and response.status == 403:
            print("❌ 403 Forbidden — valószínűleg a cookie érvénytelen vagy a böngésző fingerprint blokkolt.")
            print("ℹ️ Próbáld új cookie fájl generálását ugyanazzal a böngészővel és user-agenttel, ahonnan a cookie származik.")
            return

        wait_with_jitter(page, config.INITIAL_PAGE_WAIT_MS)
        try:
            page.wait_for_selector("div[role='listitem']", timeout=15000)
        except PWTimeout:
            print("❌ Nem sikerült betölteni a galériát – ellenőrizd a cookie fájlt.")
            return

        cards_locator = page.locator("//div[contains(@class,'group/media-post-masonry-card')]")
        processed_ids = set()
        pending_queue: List[str] = []
        pending_set = set()
        processed_count = 0
        no_new_card_scrolls = 0
        upscale_failures: List[str] = []
        download_failures: List[tuple] = []

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

                    action, media_info = decide_media_action(identifier)

                    if action == "skip_image":
                        print(f"⏭️  Már lementett kép: {media_info.image_path}")
                        processed_ids.add(identifier)
                        continue
                    if action == "skip_video":
                        width_txt = f"{media_info.video_width}px" if media_info.video_width else "ismeretlen"
                        print(f"⏭️  Már létező videó ({width_txt}): {media_info.video_path}")
                        processed_ids.add(identifier)
                        continue

                    pending_queue.append(identifier)
                    pending_set.add(identifier)
                    new_cards_added = True

                if not pending_queue:
                    if new_cards_added:
                        no_new_card_scrolls = 0
                    else:
                        no_new_card_scrolls += 1

                    attempt_txt = (
                        f" ({no_new_card_scrolls}/{config.MAX_SCROLLS_WITHOUT_NEW_CARDS})"
                        if no_new_card_scrolls
                        else ""
                    )
                    print(f"🌀 Nincs feldolgozandó kártya, görgetek tovább...{attempt_txt}")

                    previous_count = cards_locator.count()
                    wait_with_jitter(page, config.WAIT_IDLE_LOOP_MS)
                    scroll_to_load_more(page, direction="down")
                    wait_with_jitter(page, config.WAIT_IDLE_LOOP_MS)
                    current_count = cards_locator.count()
                    
                    if current_count == previous_count and no_new_card_scrolls >= config.MAX_SCROLLS_WITHOUT_NEW_CARDS:
                        print("\n🎉 Kész – minden videó feldolgozva.")
                        break
                    continue
                else:
                    no_new_card_scrolls = 0

                print(f"🔢 Hátralévő megtalált videók ({len(pending_queue)}): {config.COLOR_GRAY}{pending_queue}{config.COLOR_RESET}")

                identifier = pending_queue.pop(0)
                pending_set.discard(identifier)

                card = find_card_by_identifier(page, identifier)

                if card is None:
                    print(f"� {identifier} kártya keresése görgetésekkel...")
                    found_card = None

                    for _ in range(config.SEARCH_SCROLL_UP_ATTEMPTS):
                        scroll_to_load_more(page, direction="up")
                        found_card = find_card_by_identifier(page, identifier)
                        if found_card:
                            break

                    if found_card is None:
                        for _ in range(config.SEARCH_SCROLL_DOWN_ATTEMPTS):
                            scroll_to_load_more(page, direction="down")
                            found_card = find_card_by_identifier(page, identifier)
                            if found_card:
                                break

                    if found_card is None:
                        reason = "A kártya nem található a görgetések után"
                        print(f"⚠️  {identifier} kártya nem található, kihagyás.")
                        download_failures.append((identifier, reason))
                        processed_ids.add(identifier)
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
                no_new_card_scrolls = 0
        except Exception as error:
            print(f"❌ Folyamat megszakadt:\n\n{config.COLOR_GRAY}{error}{config.COLOR_RESET}")
            err_text = str(error).lower()
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
                browser.close()
            except Exception:
                pass


def main():
    run()
