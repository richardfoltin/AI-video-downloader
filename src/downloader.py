from __future__ import annotations

import base64
import os
import struct
from urllib.parse import urlparse
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
    IMAGE_BUTTON_SELECTOR,
    MORE_OPTIONS_BUTTON_SELECTOR,
    UPSCALE_MENU_ACTIVE_XPATH,
    UPSCALE_MENU_DISABLED_XPATH,
    VIDEO_IMAGE_TOGGLE_SELECTOR,
    click_safe_area,
    extract_video_source,
    find_card_by_identifier,
    get_card_identifier,
    scroll_to_load_more,
    wait_with_jitter,
)


def _print_error(message: str):
    print(f"{config.COLOR_RED}{message}{config.COLOR_RESET}")


def _resolve_image_src(page, identifier: str) -> str | None:
    candidate = (identifier or "").strip()
    if candidate.startswith("http"):
        return candidate
    if candidate:
        return f"https://imagine-public.x.ai/imagine-public/images/{candidate}"

    try:
        selector = config.IMAGE_FALLBACK_SELECTOR
        page.wait_for_selector(selector, timeout=config.CARD_VISIBILITY_TIMEOUT_MS)
        img_locator = page.locator(selector)
        if img_locator.count() > 0:
            src = img_locator.first.get_attribute("src")
            if src:
                return src
    except PWTimeout:
        pass
    except Exception:
        pass
    return None


def _download_image_from_url(image_src: str, target_path: str) -> bool:
    if os.path.exists(target_path):
        try:
            os.remove(target_path)
        except OSError:
            pass

    if image_src.startswith("data:"):
        try:
            header, encoded = image_src.split(",", 1)
        except ValueError:
            _print_error(t("image_download_failed", status="invalid-data-url"))
            return False

        try:
            data = base64.b64decode(encoded)
        except Exception as decode_error:
            _print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{decode_error}{config.COLOR_RESET}"))
            return False

        try:
            with open(target_path, "wb") as handle:
                handle.write(data)
            _log_image_success(target_path)
            return True
        except OSError as os_error:
            _print_error(t("image_write_failed", error=f"{config.COLOR_GRAY}{os_error}{config.COLOR_RESET}"))
            return False

    parsed = urlparse(image_src)
    if parsed.scheme not in {"http", "https"}:
        _print_error(t("image_download_failed", status="invalid-url"))
        return False

    headers = dict(config.ASSET_BASE_HEADERS)
    headers["user-agent"] = config.USER_AGENT

    try:
        response = requests.get(image_src, headers=headers, timeout=config.HTTP_REQUEST_TIMEOUT_SEC)
    except requests.RequestException as request_error:
        _print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{request_error}{config.COLOR_RESET}"))
        return False

    if not response.ok:
        _print_error(t("image_download_failed", status=response.status_code))
        return False

    try:
        with open(target_path, "wb") as file_handle:
            file_handle.write(response.content)
        _log_image_success(target_path)
        return True
    except OSError as os_error:
        _print_error(t("image_write_failed", error=f"{config.COLOR_GRAY}{os_error}{config.COLOR_RESET}"))
        return False


def _download_image_via_http(page, identifier: str, target_path: str) -> bool:
    image_src = _resolve_image_src(page, identifier)
    if not image_src:
        _print_error(t("no_image_src"))
        return False
    return _download_image_from_url(image_src, target_path)


def _download_image_from_popup(popup, target_path: str) -> bool:
    try:
        popup.wait_for_load_state("load", timeout=5000)
    except PWTimeout:
        pass

    image_src = None
    try:
        img_locator = popup.locator("img[src]")
        if img_locator.count() > 0:
            image_src = img_locator.first.get_attribute("src")
    except Exception:
        image_src = None

    if not image_src:
        image_src = popup.url

    if not image_src:
        return False

    return _download_image_from_url(image_src, target_path)


def _handle_image_popup(page, identifier: str, target_path: str, before_pages: set) -> bool:
    new_pages = [p for p in page.context.pages if p not in before_pages]

    for popup in new_pages:
        try:
            if _download_image_from_popup(popup, target_path):
                return True
        finally:
            try:
                popup.close()
            except Exception:
                pass

    return _download_image_via_http(page, identifier, target_path)


def _read_image_resolution(path: str) -> tuple[int | None, int | None]:
    try:
        with open(path, "rb") as file_handle:
            header = file_handle.read(32)

            if len(header) < 10:
                return None, None

            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                width, height = struct.unpack(">II", header[16:24])
                return int(width), int(height)

            if header[:6] in (b"GIF87a", b"GIF89a"):
                width, height = struct.unpack("<HH", header[6:10])
                return int(width), int(height)

            if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
                file_handle.seek(12)
                while True:
                    chunk_header = file_handle.read(8)
                    if len(chunk_header) < 8:
                        break
                    chunk_type = chunk_header[:4]
                    chunk_size = struct.unpack("<I", chunk_header[4:])[0]
                    chunk_data = file_handle.read(chunk_size + (chunk_size & 1))
                    if len(chunk_data) < chunk_size:
                        break
                    if chunk_type == b"VP8X" and len(chunk_data) >= 10:
                        width = 1 + ((chunk_data[4]) | (chunk_data[5] << 8) | (chunk_data[6] << 16))
                        height = 1 + ((chunk_data[7]) | (chunk_data[8] << 8) | (chunk_data[9] << 16))
                        return int(width), int(height)
                    if chunk_type == b"VP8 " and len(chunk_data) >= 10:
                        width = (chunk_data[6] << 8) | chunk_data[7]
                        height = (chunk_data[8] << 8) | chunk_data[9]
                        return int(width & 0x3FFF), int(height & 0x3FFF)
                    if chunk_type == b"VP8L" and len(chunk_data) >= 5:
                        bits = struct.unpack("<I", chunk_data[:4])[0]
                        width = (bits & 0x3FFF) + 1
                        height = ((bits >> 14) & 0x3FFF) + 1
                        return int(width), int(height)

            if header[:2] == b"\xff\xd8":
                file_handle.seek(2)
                while True:
                    marker_prefix = file_handle.read(1)
                    if not marker_prefix:
                        break
                    if marker_prefix != b"\xff":
                        continue
                    marker = file_handle.read(1)
                    while marker == b"\xff":
                        marker = file_handle.read(1)
                    if not marker:
                        break
                    if marker in b"\xc0\xc1\xc2\xc3\xc5\xc6\xc7\xc9\xca\xcb\xcd\xce\xcf":
                        length_bytes = file_handle.read(2)
                        if len(length_bytes) != 2:
                            break
                        segment_length = struct.unpack(">H", length_bytes)[0]
                        precision_byte = file_handle.read(1)
                        if len(precision_byte) != 1:
                            break
                        frame_data = file_handle.read(4)
                        if len(frame_data) == 4:
                            height, width = struct.unpack(">HH", frame_data)
                            return int(width), int(height)
                        break
                    if marker == b"\xda":
                        break
                    length_bytes = file_handle.read(2)
                    if len(length_bytes) != 2:
                        break
                    length = struct.unpack(">H", length_bytes)[0]
                    file_handle.seek(length - 2, 1)

    except OSError:
        return None, None

    return None, None


def _log_image_success(path: str):
    width, height = _read_image_resolution(path)
    if width is not None and height is not None:
        resolution = f"({width}×{height})"
    else:
        resolution = f"({t('image_resolution_unknown')})"
    filename = os.path.basename(path)
    accent_name = f"{config.COLOR_ACCENT}{filename}{config.COLOR_RESET}"
    print(t("image_download_success", name=accent_name, resolution=resolution))


def _attempt_video_fallback(page, filepath: str, filename: str, record_failure) -> bool:
    fallback_url = extract_video_source(page)
    if not fallback_url:
        record_failure(t("video_src_not_found"))
        return False

    print(t("alternative_download", url=fallback_url))

    try:
        api_resp = page.context.request.get(
            fallback_url,
            headers={
                "user-agent": config.USER_AGENT,
                "accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                "referer": config.FAVORITES_URL,
                "range": "bytes=0-",
            },
        )
        if api_resp.ok:
            content = api_resp.body()
            with open(filepath, "wb") as handle:
                handle.write(content)

            alt_size = os.path.getsize(filepath)
            if alt_size == 0:
                record_failure(t("alternative_download_zero_byte"))
                return False
            print(t("alternative_download_success", filename=filename, size=alt_size))
            return True
    except Exception:
        pass

    try:
        with page.expect_download(timeout=config.DOWNLOAD_BUTTON_TIMEOUT_MS) as dl_info:
            page.evaluate(
                "(url) => { const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); }",
                fallback_url,
            )
        download = dl_info.value
        download.save_as(filepath)
        if os.path.getsize(filepath) > 0:
            print(t("alternative_download_success", filename=filename, size=os.path.getsize(filepath)))
            return True
    except Exception:
        pass

    headers = {
        "user-agent": config.USER_AGENT,
        "accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
        "referer": config.FAVORITES_URL,
        "range": "bytes=0-",
    }

    try:
        try:
            cookie_header = load_cookie_header(config.COOKIE_FILE)
        except Exception:
            cookie_header = None
        if cookie_header:
            headers["cookie"] = cookie_header

        response = requests.get(
            fallback_url,
            stream=True,
            headers=headers,
            timeout=config.HTTP_REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as req_err:
        record_failure(t("alternative_download_http_error", error=f"{config.COLOR_GRAY}{req_err}{config.COLOR_RESET}"))
        return False

    if not response.ok:
        record_failure(t("alternative_download_failed", status=response.status_code))
        return False

    with open(filepath, "wb") as handle:
        for chunk in response.iter_content(1024 * 1024):
            handle.write(chunk)

    alt_size = os.path.getsize(filepath)
    if alt_size == 0:
        record_failure(t("alternative_download_zero_byte"))
        return False

    print(t("alternative_download_success", filename=filename, size=alt_size))
    return True


def _card_has_video_toggle(page) -> bool:
    try:
        page.wait_for_selector(VIDEO_IMAGE_TOGGLE_SELECTOR, timeout=config.VIDEO_IMAGE_TOGGLE_TIMEOUT_MS)
    except PWTimeout:
        return False
    try:
        return page.locator(VIDEO_IMAGE_TOGGLE_SELECTOR).count() > 0
    except Exception:
        return False


def _card_has_image_button(page) -> bool:
    try:
        page.wait_for_selector(IMAGE_BUTTON_SELECTOR, timeout=config.VIDEO_IMAGE_TOGGLE_TIMEOUT_MS)
    except PWTimeout:
        return False
    try:
        return page.locator(IMAGE_BUTTON_SELECTOR).count() > 0
    except Exception:
        return False


def _media_requirements(media_info) -> tuple[bool, bool]:
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


def download_video_for_card(
    page,
    identifier: str,
    media_info,
    item_index: int,
    upscale_failures: List[str],
    record_failure,
) -> bool:
    if config.UPSCALE_VIDEOS:
        page.wait_for_selector(MORE_OPTIONS_BUTTON_SELECTOR, timeout=config.MORE_OPTIONS_BUTTON_TIMEOUT_MS)
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
                page.wait_for_selector(config.HD_BUTTON_SELECTOR, timeout=config.UPSCALE_TIMEOUT_MS)
                print(t("upscale_success"))
            except PWTimeout:
                print(t("upscale_timeout"))
                upscale_failures.append(identifier)

        wait_with_jitter(page, config.WAIT_AFTER_MENU_INTERACTION_MS)
    else:
        print(t("upscale_disabled"))

    dl_button = page.locator(DOWNLOAD_BUTTON_SELECTOR)
    if dl_button.count() == 0:
        record_failure(t("no_download_button"))
        return False

    video_path = media_info.video_path
    video_filename = os.path.basename(video_path)
    accent_video_filename = f"{config.COLOR_ACCENT}{video_filename}{config.COLOR_RESET}"
    button = dl_button.first
    button.wait_for(state="visible", timeout=config.DOWNLOAD_BUTTON_TIMEOUT_MS)

    if os.path.exists(video_path):
        print(t("already_exists_overwrite", filename=video_filename))
        try:
            os.remove(video_path)
        except OSError as remove_err:
            record_failure(t("delete_existing_failed", error=remove_err))
            return False

    download_event = None
    fallback_needed = False

    try:
        with page.expect_download(timeout=config.DOWNLOAD_BUTTON_TIMEOUT_MS) as dl_info:
            button.click()
        download_event = dl_info.value
    except PWTimeout:
        fallback_needed = True
    except Exception as error:
        record_failure(
            t(
                "video_processing_error",
                index=item_index + 1,
                error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}",
            )
        )
        fallback_needed = True

    if download_event is not None:
        try:
            download_event.save_as(video_path)
            if os.path.getsize(video_path) == 0:
                print(t("zero_byte_file_delete_retry"))
                try:
                    os.remove(video_path)
                except OSError as remove_err:
                    record_failure(t("zero_byte_file_delete_failed", error=remove_err))
                    return False
                fallback_needed = True
            else:
                print(t("download_success", filename=accent_video_filename))
                return True
        except Exception as error:
            record_failure(
                t(
                    "video_processing_error",
                    index=item_index + 1,
                    error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}",
                )
            )
            return False

    if not fallback_needed:
        return False

    if _attempt_video_fallback(page, video_path, video_filename, record_failure):
        return True

    return False


def download_image_for_card(
    page,
    identifier: str,
    media_info,
    has_video_option: bool,
    record_failure,
) -> bool:
    if has_video_option:
        if not _card_has_image_button(page):
            print(t("no_image_element"))
        else:
            img_button = page.locator(IMAGE_BUTTON_SELECTOR)
            try:
                img_button.first.click()
                wait_with_jitter(page, config.WAIT_AFTER_MENU_INTERACTION_MS)
            except Exception:
                print(t("no_image_element"))

    dl_button = page.locator(DOWNLOAD_BUTTON_SELECTOR)
    if dl_button.count() == 0:
        record_failure(t("no_download_button"))
        return False

    button = dl_button.first
    button.wait_for(state="visible", timeout=config.DOWNLOAD_BUTTON_TIMEOUT_MS)
    image_path = media_info.image_path
    before_pages = set(page.context.pages)
    success = False

    try:
        with page.expect_download(timeout=config.DOWNLOAD_BUTTON_TIMEOUT_MS) as dl_info:
            button.click()
        download = dl_info.value

        try:
            download.save_as(image_path)
            if os.path.getsize(image_path) == 0:
                try:
                    os.remove(image_path)
                except OSError:
                    pass
                success = _handle_image_popup(page, identifier, image_path, before_pages)
            else:
                _log_image_success(image_path)
                success = True
        except Exception as error:
            _print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}"))
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except OSError:
                pass
            success = _handle_image_popup(page, identifier, image_path, before_pages)

    except PWTimeout:
        success = _handle_image_popup(page, identifier, image_path, before_pages)
    except Exception as error:
        _print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}"))
        success = _handle_image_popup(page, identifier, image_path, before_pages)
    finally:
        new_pages = [p for p in page.context.pages if p not in before_pages]
        for popup in new_pages:
            try:
                popup.close()
            except Exception:
                pass

    if success:
        return True

    record_failure(t("image_download_error", error=f"{config.COLOR_GRAY}UI download failed{config.COLOR_RESET}"))
    return False


def process_one_card(
    page,
    card,
    index: int,
    identifier: str,
    upscale_failures: List[str],
    download_failures: List[tuple],
    media_info,
):
    need_video_download, need_image_download = _media_requirements(media_info)

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
        _print_error(t("download_error", reason=reason))
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
        has_video_option = _card_has_video_toggle(page)

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
        _print_error(t("no_media_enabled"))
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
            _print_error(t("forbidden_error"))
            print(t("forbidden_help"))
            return

        wait_with_jitter(page, config.INITIAL_PAGE_WAIT_MS)
        try:
            page.wait_for_selector(config.GALLERY_LISTITEM_SELECTOR, timeout=config.GALLERY_LOAD_TIMEOUT_MS)
        except PWTimeout:
            _print_error(t("gallery_load_failed"))
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
                    need_video_download, need_image_download = _media_requirements(media_info)

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
                        _print_error(t("card_not_found_after_scroll", identifier=identifier))
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
            _print_error(combined)
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
