from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from . import config
from .cookies import cookie_header_to_list, load_cookie_header
from .image_downloader import download_image_for_card
from .localization import print_error, t
from .playwright_utils import (
    BACK_BUTTON_SELECTOR,
    find_card_by_identifier,
    get_card_identifier,
    scroll_to_load_more,
    wait_with_jitter,
)
from .video_downloader import card_has_video_toggle, download_video_for_card, probe_video_width


@dataclass
class MediaCheckResult:
    image_path: str
    image_exists: bool
    video_path: str
    video_exists: bool
    video_width: Optional[int]


def decide_media_action(image_filename: str) -> tuple[str, MediaCheckResult]:
    name_without_ext, _ = os.path.splitext(image_filename)
    image_path = os.path.join(config.DOWNLOAD_DIR, f"grok-image-{name_without_ext}.png")
    video_path = os.path.join(config.DOWNLOAD_DIR, f"grok-video-{name_without_ext}.mp4")

    image_exists = os.path.exists(image_path)
    video_exists = os.path.exists(video_path)
    video_width = probe_video_width(video_path) if video_exists else None

    info = MediaCheckResult(
        image_path=image_path,
        image_exists=image_exists,
        video_path=video_path,
        video_exists=video_exists,
        video_width=video_width,
    )

    if info.image_exists and not info.video_exists:
        if config.DOWNLOAD_IMAGES:
            return "process", info
        return "skip_image", info

    if info.video_exists:
        if info.video_width is None:
            return "process", info
        if info.video_width >= config.UPSCALE_VIDEO_WIDTH:
            return "skip_video", info
        return "process", info

    return "process", info


def media_requirements(media_info: MediaCheckResult) -> Tuple[bool, bool]:
    need_video = (
        config.DOWNLOAD_VIDEOS
        and (
            not media_info.video_exists
            or (
                config.UPSCALE_VIDEOS
                and (
                    media_info.video_width is None
                    or media_info.video_width < config.UPSCALE_VIDEO_WIDTH
                )
            )
        )
    )
    need_image = config.DOWNLOAD_IMAGES and not media_info.image_exists
    return need_video, need_image


def process_one_card(
    page,
    card,
    index: int,
    identifier: str,
    upscale_failures: List[str],
    download_failures: List[tuple],
    media_info,
):
    need_video_download, need_image_download = media_requirements(media_info)

    if not need_video_download and not need_image_download:
        details = []
        if media_info.video_exists:
            details.append(f"🎞️ {config.COLOR_ACCENT}{media_info.video_path}{config.COLOR_RESET}")
        if media_info.image_exists:
            details.append(f"🖼️ {config.COLOR_ACCENT}{media_info.image_path}{config.COLOR_RESET}")
        if details:
            joined = "\n   ".join(details)
            print(t("all_media_downloaded_detailed", details=joined))
        else:
            print(t("all_media_downloaded", identifier=identifier))
        return

    print(f"\n{t('card_processing', index=index + 1, identifier=identifier)}")

    def record_failure(reason: str):
        print_error(t("download_error", reason=reason))
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
        has_video_option = card_has_video_toggle(page)

        if need_video_download:
            if not has_video_option:
                print(t("skipping_no_video_option", identifier=identifier))
            else:
                if download_video_for_card(page, identifier, media_info, index, upscale_failures, record_failure):
                    media_info.video_exists = True

        if need_image_download:
            if download_image_for_card(page, identifier, media_info, has_video_option, record_failure):
                media_info.image_exists = True

    except Exception as error:
        record_failure(t("video_processing_error", index=index + 1, error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}"))

    finally:
        try:
            back_button = page.locator(BACK_BUTTON_SELECTOR).first
            back_button.wait_for(state="visible", timeout=config.BACK_BUTTON_TIMEOUT_MS)
            wait_with_jitter(page, config.WAIT_AFTER_BACK_BUTTON_MS)
            back_button.click()
            page.wait_for_selector(config.GALLERY_LISTITEM_SELECTOR, timeout=config.GALLERY_LOAD_TIMEOUT_MS)
            print(t("back_to_gallery"))
        except Exception:
            print(t("back_failed_continue"))
        wait_with_jitter(page, config.WAIT_AFTER_BACK_BUTTON_MS)


def run():
    if not config.DOWNLOAD_VIDEOS and not config.DOWNLOAD_IMAGES:
        print_error(t("no_media_enabled"))
        return

    cookie_header = load_cookie_header(config.COOKIE_FILE)
    cookies = cookie_header_to_list(cookie_header, ".grok.com")

    with sync_playwright() as playwright:
        launch_args = config.BROWSER_LAUNCH_ARGS
        browser = playwright.chromium.launch(channel=config.BROWSER_CHANNEL, headless=config.HEADLESS, args=launch_args)
        context = browser.new_context(accept_downloads=True, user_agent=config.USER_AGENT, viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT}, locale=config.BROWSER_LOCALE, timezone_id=config.BROWSER_TIMEZONE, color_scheme=config.BROWSER_COLOR_SCHEME, extra_http_headers=config.CONTEXT_HEADERS)
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
            print_error(t("forbidden_error"))
            print(t("forbidden_help"))
            return

        wait_with_jitter(page, config.INITIAL_PAGE_WAIT_MS)
        try:
            page.wait_for_selector(config.GALLERY_LISTITEM_SELECTOR, timeout=config.GALLERY_LOAD_TIMEOUT_MS)
        except PWTimeout:
            print_error(t("gallery_load_failed"))
            return

        cards_locator = page.locator(config.CARDS_XPATH)
        processed_ids = set()
        pending_queue = []
        pending_set = set()
        processed_count = 0
        no_new_card_scrolls = 0
        upscale_failures: List[str] = []
        download_failures: List[tuple] = []

        try:
            while True:
                card_count = cards_locator.count()
                any_new_cards_found = False

                for idx in range(card_count):
                    card = cards_locator.nth(idx)
                    identifier = get_card_identifier(card)
                    if not identifier or identifier == "No ID":
                        continue
                    if identifier in processed_ids or identifier in pending_set:
                        continue

                    # Found any new card (whether we process it or skip it)
                    any_new_cards_found = True

                    _, media_info = decide_media_action(identifier)
                    need_video_download, need_image_download = media_requirements(media_info)

                    if not (need_video_download or need_image_download):
                        details = []
                        if media_info.video_exists:
                            details.append(f"🎞️ {config.COLOR_ACCENT}{media_info.video_path}{config.COLOR_RESET}")
                        if media_info.image_exists:
                            details.append(f"🖼️ {config.COLOR_ACCENT}{media_info.image_path}{config.COLOR_RESET}")
                        if details:
                            joined = "\n   ".join(details)
                            print(t("all_media_downloaded_detailed", details=joined))
                        else:
                            print(t("all_media_downloaded", identifier=identifier))
                        processed_ids.add(identifier)
                        continue

                    pending_queue.append((identifier, media_info))
                    pending_set.add(identifier)

                if not pending_queue:
                    no_new_card_scrolls = 0 if any_new_cards_found else no_new_card_scrolls + 1

                    if no_new_card_scrolls >= config.MAX_SCROLLS_WITHOUT_NEW_CARDS:
                        print(f"\n{t('processing_complete')}")
                        break
                    else:
                        attempt_txt = f" ({no_new_card_scrolls + 1}/{config.MAX_SCROLLS_WITHOUT_NEW_CARDS})"
                        print(f"{t('no_cards_scroll')}{attempt_txt}")

                        wait_with_jitter(page, config.WAIT_IDLE_LOOP_MS)
                        scroll_to_load_more(page, direction="down")
                        wait_with_jitter(page, config.WAIT_IDLE_LOOP_MS)
                        continue
                else:
                    no_new_card_scrolls = 0

                queue_preview = [item[0] for item in pending_queue]
                print(t("remaining_videos", count=len(pending_queue), queue=f"{config.COLOR_GRAY}{queue_preview}{config.COLOR_RESET}"))

                identifier, media_info = pending_queue.pop(0)
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
                        print_error(t("card_not_found_after_scroll", identifier=identifier))
                        download_failures.append((identifier, reason))
                        processed_ids.add(identifier)
                        continue

                    card = found_card

                process_one_card(page, card, processed_count, identifier, upscale_failures, download_failures, media_info)
                processed_ids.add(identifier)
                processed_count += 1
                no_new_card_scrolls = 0
        except Exception as error:
            combined = f"{t('process_interrupted')}\n\n{config.COLOR_GRAY}{error}{config.COLOR_RESET}"
            print_error(combined)
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
