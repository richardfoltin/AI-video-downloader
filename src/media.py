from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

from . import config
from .localization import t

_FFPROBE_AVAILABLE: Optional[bool] = None


@dataclass
class MediaCheckResult:
    image_path: str
    image_exists: bool
    video_path: str
    video_exists: bool
    video_width: Optional[int]


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
            print(t("ffprobe_not_found"))
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


def analyze_existing_media(image_filename: str) -> MediaCheckResult:
    name_without_ext, _ = os.path.splitext(image_filename)
    image_path = os.path.join(config.DOWNLOAD_DIR, f"grok-image-{name_without_ext}.png")
    video_path = os.path.join(config.DOWNLOAD_DIR, f"grok-video-{name_without_ext}.mp4")

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


def decide_media_action(image_filename: str, has_video_option: bool = True) -> Tuple[str, MediaCheckResult]:
    info = analyze_existing_media(image_filename)

    # If no video option available in the card
    if not has_video_option:
        if not config.SKIP_IMAGES:
            # Download image if it doesn't exist
            if not info.image_exists:
                return "process_image", info
            else:
                return "skip_image", info
        else:
            # Skip this card entirely if no video option and not downloading images
            return "skip_no_video", info

    # Original logic for cards with video option
    if info.image_exists and not info.video_exists:
        return "skip_image", info

    if info.video_exists:
        if info.video_width is None:
            return "process", info
        if info.video_width >= config.UPSCALE_VIDEO_WIDTH:
            return "skip_video", info
        return "process", info

    return "process", info
