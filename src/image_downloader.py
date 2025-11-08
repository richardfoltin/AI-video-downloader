from __future__ import annotations

import base64
import os
import struct
from urllib.parse import urlparse

import requests
from playwright.sync_api import TimeoutError as PWTimeout

from . import config
from .localization import t, print_error
from .playwright_utils import DOWNLOAD_BUTTON_SELECTOR, IMAGE_BUTTON_SELECTOR, wait_with_jitter


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
            print_error(t("image_download_failed", status="invalid-data-url"))
            return False

        try:
            data = base64.b64decode(encoded)
        except Exception as decode_error:
            print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{decode_error}{config.COLOR_RESET}"))
            return False

        try:
            with open(target_path, "wb") as handle:
                handle.write(data)
            _log_image_success(target_path)
            return True
        except OSError as os_error:
            print_error(t("image_write_failed", error=f"{config.COLOR_GRAY}{os_error}{config.COLOR_RESET}"))
            return False

    parsed = urlparse(image_src)
    if parsed.scheme not in {"http", "https"}:
        print_error(t("image_download_failed", status="invalid-url"))
        return False

    headers = dict(config.ASSET_BASE_HEADERS)
    headers["user-agent"] = config.USER_AGENT

    try:
        response = requests.get(image_src, headers=headers, timeout=config.HTTP_REQUEST_TIMEOUT_SEC)
    except requests.RequestException as request_error:
        print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{request_error}{config.COLOR_RESET}"))
        return False

    if not response.ok:
        print_error(t("image_download_failed", status=response.status_code))
        return False

    try:
        with open(target_path, "wb") as file_handle:
            file_handle.write(response.content)
        _log_image_success(target_path)
        return True
    except OSError as os_error:
        print_error(t("image_write_failed", error=f"{config.COLOR_GRAY}{os_error}{config.COLOR_RESET}"))
        return False


def _download_image_via_http(page, identifier: str, target_path: str) -> bool:
    image_src = _resolve_image_src(page, identifier)
    if not image_src:
        print_error(t("no_image_src"))
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
                        struct.unpack(">H", length_bytes)[0]
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


def _log_image_success(path: str) -> None:
    width, height = _read_image_resolution(path)
    if width is not None and height is not None:
        resolution = f"({width}×{height})"
    else:
        resolution = f"({t('image_resolution_unknown')})"
    filename = os.path.basename(path)
    accent_name = f"{config.COLOR_ACCENT}{filename}{config.COLOR_RESET}"
    print(t("image_download_success", name=accent_name, resolution=resolution))


def _card_has_image_button(page) -> bool:
    try:
        page.wait_for_selector(IMAGE_BUTTON_SELECTOR, timeout=config.VIDEO_IMAGE_TOGGLE_TIMEOUT_MS)
    except PWTimeout:
        return False
    try:
        return page.locator(IMAGE_BUTTON_SELECTOR).count() > 0
    except Exception:
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
            print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}"))
            try:
                if os.path.exists(image_path):
                    os.remove(image_path)
            except OSError:
                pass
            success = _handle_image_popup(page, identifier, image_path, before_pages)

    except PWTimeout:
        success = _handle_image_popup(page, identifier, image_path, before_pages)
    except Exception as error:
        print_error(t("image_download_error", error=f"{config.COLOR_GRAY}{error}{config.COLOR_RESET}"))
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


__all__ = ["download_image_for_card"]
