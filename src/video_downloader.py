from __future__ import annotations

import json
import os
import subprocess
from typing import List, Optional

import requests
from playwright.sync_api import TimeoutError as PWTimeout

from . import config
from .cookies import load_cookie_header
from .localization import print_error, t
from .playwright_utils import (
    DOWNLOAD_BUTTON_SELECTOR,
    MORE_OPTIONS_BUTTON_SELECTOR,
    UPSCALE_MENU_ACTIVE_XPATH,
    UPSCALE_MENU_DISABLED_XPATH,
    VIDEO_IMAGE_TOGGLE_SELECTOR,
    click_safe_area,
    extract_video_source,
    wait_with_jitter,
)


_FFPROBE_AVAILABLE: Optional[bool] = None


def _run_ffprobe(path: str) -> Optional[str]:
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
        return None
    except subprocess.CalledProcessError:
        return ""
    return result.stdout


def probe_video_width(path: str) -> Optional[int]:
    global _FFPROBE_AVAILABLE

    if _FFPROBE_AVAILABLE is False:
        return None

    payload_text = _run_ffprobe(path)
    if payload_text is None:
        if _FFPROBE_AVAILABLE is not False:
            _FFPROBE_AVAILABLE = False
            print_error(t("ffprobe_not_found"))
        return None
    if payload_text == "":
        return None

    _FFPROBE_AVAILABLE = True

    try:
        payload = json.loads(payload_text)
        streams = payload.get("streams", [])
        if streams:
            width_value = streams[0].get("width")
            if width_value is not None:
                return int(width_value)
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    return None


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


def card_has_video_toggle(page) -> bool:
    try:
        page.wait_for_selector(VIDEO_IMAGE_TOGGLE_SELECTOR, timeout=config.VIDEO_IMAGE_TOGGLE_TIMEOUT_MS)
    except PWTimeout:
        return False
    try:
        return page.locator(VIDEO_IMAGE_TOGGLE_SELECTOR).count() > 0
    except Exception:
        return False


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
                print_error(t("zero_byte_file_delete_retry"))
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


__all__ = ["download_video_for_card", "card_has_video_toggle", "probe_video_width"]
