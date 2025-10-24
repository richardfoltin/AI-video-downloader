from __future__ import annotations

import os
from typing import List

import requests
from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from . import config
from .cookies import cookie_header_to_list, load_cookie_header
from .localization import t
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


def process_one_card(
    page,
    card,
    index: int,
    identifier: str,
    upscale_failures: List[str],
    download_failures: List[tuple],
):
    print(f"\n{t('card_processing', index=index + 1, identifier=identifier)}")

    def record_failure(reason: str):
        print(t("download_error", reason=reason))
        download_failures.append((identifier, reason))

    for attempt in range(2):
        try:
            card.scroll_into_view_if_needed()
            card.wait_for(state="visible", timeout=config.CARD_VISIBILITY_TIMEOUT_MS)
            wait_with_jitter(page, config.WAIT_AFTER_CARD_SCROLL_MS)
            card.click()
            print(t("card_click"))
            break
        except PWTimeout:
            if attempt == 0:
                print(t("card_disappeared_retry"))
                refreshed = find_card_by_identifier(page, identifier)
                if refreshed is None:
                    record_failure(t("card_not_found_for_clicking"))
                    return
                card = refreshed
                continue
            record_failure(t("card_click_timeout"))
            return

    try:
        page.wait_for_selector(
            MORE_OPTIONS_BUTTON_SELECTOR, timeout=config.MORE_OPTIONS_BUTTON_TIMEOUT_MS
        )
        page.locator(MORE_OPTIONS_BUTTON_SELECTOR).first.click()
        print(t("menu_opened"))

        disabled = page.locator(UPSCALE_MENU_DISABLED_XPATH)
        active = page.locator(UPSCALE_MENU_ACTIVE_XPATH)
        wait_with_jitter(page, config.WAIT_AFTER_CARD_SCROLL_MS)

        if disabled.count() > 0:
            print(t("already_upscaled"))
            click_safe_area(page)
        else:
            print(t("upscale_start"))
            active.first.click()
            wait_with_jitter(page, config.WAIT_AFTER_MENU_INTERACTION_MS)
            click_safe_area(page)
            try:
                page.wait_for_selector(
                    config.HD_BUTTON_SELECTOR, timeout=config.UPSCALE_TIMEOUT_MS
                )
                print(t("upscale_success"))
            except PWTimeout:
                print(t("upscale_timeout"))
                upscale_failures.append(identifier)

        wait_with_jitter(page, config.WAIT_AFTER_MENU_INTERACTION_MS)

        dl_button = page.locator(DOWNLOAD_BUTTON_SELECTOR)
        if dl_button.count() == 0:
            record_failure(t("no_download_button"))
            return
        dl_button.first.wait_for(
            state="visible", timeout=config.DOWNLOAD_BUTTON_TIMEOUT_MS
        )

        with page.expect_download() as dl_info:
            dl_button.first.click()
        download = dl_info.value

        filename = (
            download.suggested_filename
            or config.DEFAULT_FILENAME_PATTERN.format(index=index + 1)
        )
        filepath = os.path.join(config.DOWNLOAD_DIR, filename)

        if os.path.exists(filepath):
            print(t("already_exists_overwrite", filename=filename))
            try:
                os.remove(filepath)
            except OSError as remove_err:
                record_failure(t("delete_existing_failed", error=remove_err))
                return

        download.save_as(filepath)

        if os.path.getsize(filepath) == 0:
            print(t("zero_byte_file_delete_retry"))
            try:
                os.remove(filepath)
            except OSError as remove_err:
                record_failure(t("zero_byte_file_delete_failed", error=remove_err))
                return

            fallback_url = extract_video_source(page)
            if not fallback_url:
                record_failure(t("video_src_not_found"))
                return

            print(t("alternative_download", url=fallback_url))

            headers = {
                "user-agent": config.USER_AGENT,
                "accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                "referer": config.FAVORITES_URL,
            }

            try:
                response = requests.get(
                    fallback_url,
                    stream=True,
                    headers=headers,
                    timeout=config.HTTP_REQUEST_TIMEOUT_SEC,
                )
            except requests.RequestException as req_err:
                record_failure(
                    t(
                        "alternative_download_http_error",
                        error=f"{config.COLOR_GRAY}{req_err}{config.COLOR_RESET}",
                    )
                )
                return

            if not response.ok:
                record_failure(
                    t("alternative_download_failed", status=response.status_code)
                )
                return

            with open(filepath, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)

            alt_size = os.path.getsize(filepath)
            if alt_size == 0:
                record_failure(t("alternative_download_zero_byte"))
                return
            print(t("alternative_download_success", filename=filename, size=alt_size))
        else:
            print(t("download_success", filename=filename))

    except Exception as error:
        record_failure(
            t(
                "video_processing_error",
                index=index + 1,
                error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}",
            )
        )

    finally:
        try:
            back_button = page.locator(BACK_BUTTON_SELECTOR).first
            back_button.wait_for(state="visible", timeout=config.BACK_BUTTON_TIMEOUT_MS)
            wait_with_jitter(page, config.WAIT_AFTER_BACK_BUTTON_MS)
            back_button.click()
            page.wait_for_selector(
                config.GALLERY_LISTITEM_SELECTOR, timeout=config.GALLERY_LOAD_TIMEOUT_MS
            )
            print(t("back_to_gallery"))
        except Exception:
            print(t("back_failed_continue"))
        wait_with_jitter(page, config.WAIT_AFTER_BACK_BUTTON_MS)


def run():
    cookie_header = load_cookie_header(config.COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, ".grok.com")

    with sync_playwright() as playwright:
        launch_args = config.BROWSER_LAUNCH_ARGS
        browser = playwright.chromium.launch(
            channel=config.BROWSER_CHANNEL, headless=config.HEADLESS, args=launch_args
        )
        context = browser.new_context(
            accept_downloads=True,
            user_agent=config.USER_AGENT,
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            locale=config.BROWSER_LOCALE,
            timezone_id=config.BROWSER_TIMEZONE,
            color_scheme=config.BROWSER_COLOR_SCHEME,
            extra_http_headers=config.CONTEXT_HEADERS,
        )
        context.add_cookies(cookies)
        page = context.new_page()

        if config.ENABLE_ASSET_ROUTING:

            def asset_header_rewrite(route, request):
                headers = dict(request.headers)
                headers.update(config.ASSET_BASE_HEADERS)
                headers.setdefault("user-agent", config.USER_AGENT)
                route.continue_(headers=headers)

            page.route(config.ASSET_URL_PATTERN, asset_header_rewrite)

        page.add_init_script(config.INIT_SCRIPT)

        print(t("gallery_opening"))
        response = page.goto(config.FAVORITES_URL, wait_until="domcontentloaded")

        if response and response.status == 403:
            print(t("forbidden_error"))
            print(t("forbidden_help"))
            return

        wait_with_jitter(page, config.INITIAL_PAGE_WAIT_MS)
        try:
            page.wait_for_selector(
                config.GALLERY_LISTITEM_SELECTOR, timeout=config.GALLERY_LOAD_TIMEOUT_MS
            )
        except PWTimeout:
            print(t("gallery_load_failed"))
            return

        cards_locator = page.locator(config.CARDS_XPATH)
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
                        print(t("already_downloaded_image", path=media_info.image_path))
                        processed_ids.add(identifier)
                        continue
                    if action == "skip_video":
                        width_txt = (
                            f"{media_info.video_width}px"
                            if media_info.video_width
                            else t("video_width_unknown")
                        )
                        print(
                            t(
                                "already_downloaded_video",
                                width=width_txt,
                                path=media_info.video_path,
                            )
                        )
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
                    print(f"{t('no_cards_scroll')}{attempt_txt}")

                    previous_count = cards_locator.count()
                    wait_with_jitter(page, config.WAIT_IDLE_LOOP_MS)
                    scroll_to_load_more(page, direction="down")
                    wait_with_jitter(page, config.WAIT_IDLE_LOOP_MS)
                    current_count = cards_locator.count()

                    if (
                        current_count == previous_count
                        and no_new_card_scrolls >= config.MAX_SCROLLS_WITHOUT_NEW_CARDS
                    ):
                        print(f"\n{t('processing_complete')}")
                        break
                    continue
                else:
                    no_new_card_scrolls = 0

                print(
                    t(
                        "remaining_videos",
                        count=len(pending_queue),
                        queue=f"{config.COLOR_GRAY}{pending_queue}{config.COLOR_RESET}",
                    )
                )

                identifier = pending_queue.pop(0)
                pending_set.discard(identifier)

                card = find_card_by_identifier(page, identifier)

                if card is None:
                    print(t("card_search_scroll", identifier=identifier))
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
                        reason = t("card_not_found_reason")
                        print(t("card_not_found_after_scroll", identifier=identifier))
                        download_failures.append((identifier, reason))
                        processed_ids.add(identifier)
                        continue

                    card = found_card

                process_one_card(
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
            print(
                f"{t('process_interrupted')}\n\n{config.COLOR_GRAY}{error}{config.COLOR_RESET}"
            )
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
                print(f"\n{t('upscale_warnings')}")
                for failed in upscale_failures:
                    print(f"   • {failed}")
            else:
                print(f"\n{t('no_upscale_warnings')}")

            if download_failures:
                print(f"\n{t('download_errors')}")
                for ident, reason in download_failures:
                    print(f"   • {ident}: {reason}")
            else:
                print(f"\n{t('no_download_errors')}")
            try:
                browser.close()
            except Exception:
                pass


def main():
    run()
