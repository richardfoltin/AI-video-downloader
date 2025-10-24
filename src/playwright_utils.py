from __future__ import annotations

import random
from playwright.sync_api import TimeoutError as PWTimeout

from . import config
from .localization import t
from src import localization


def wait_with_jitter(page, base_ms: int):
    page.wait_for_timeout(base_ms + random.randint(0, config.WAIT_JITTER_MS))


def make_aria_selector(tag: str, labels):
    selectors = [f"{tag}[aria-label='{label}']" for label in labels]
    return ", ".join(selectors)


def build_menuitem_xpath(texts, disabled: bool):
    text_conditions = " or ".join([f"contains(normalize-space(.), '{text}')" for text in texts])
    disabled_clause = "@aria-disabled='true'" if disabled else "not(@aria-disabled)"
    return f"//div[@role='menuitem' and ({text_conditions}) and {disabled_clause}]"


MORE_OPTIONS_BUTTON_SELECTOR = make_aria_selector("button", localization.MORE_OPTIONS_LABELS)
DOWNLOAD_BUTTON_SELECTOR = make_aria_selector("button", localization.DOWNLOAD_BUTTON_LABELS)
BACK_BUTTON_SELECTOR = make_aria_selector("button", localization.BACK_BUTTON_LABELS)
UPSCALE_MENU_DISABLED_XPATH = build_menuitem_xpath(localization.UPSCALE_MENU_LABELS, disabled=True)
UPSCALE_MENU_ACTIVE_XPATH = build_menuitem_xpath(localization.UPSCALE_MENU_LABELS, disabled=False)
VIDEO_IMAGE_TOGGLE_SELECTOR = make_aria_selector("div", ["Text alignment"])


def scroll_to_load_more(page, direction: str = "down"):
    direction = (direction or "down").lower()
    if direction not in {"down", "up"}:
        direction = "down"

    jitter = random.randint(0, config.MOUSE_SCROLL_JITTER_MS)
    distance = config.MOUSE_SCROLL + jitter
    delta_y = distance if direction == "down" else -distance
    label = (t("scroll_direction_down") if direction == "down" else t("scroll_direction_up"))
    print(t("scrolling", direction=label))
    page.mouse.wheel(0, delta_y)
    wait_with_jitter(page, config.SCROLL_PAUSE_MS)


def click_safe_area(page):
    viewport = page.viewport_size or {"width": 1280, "height": 800}
    x = int(min(max(viewport["width"] * 0.6, 200), viewport["width"] - 80))
    y = int(min(max(viewport["height"] * 0.2, 120), viewport["height"] - 120))
    page.mouse.click(x, y)


def extract_video_source(page):
    selectors = [
        "video#hd-video[src]",
        "video#sd-video[src]",
        "video[src]",
    ]
    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=3000)
        except PWTimeout:
            continue

        locator = page.locator(selector)
        if locator.count() == 0:
            continue

        try:
            src = locator.first.get_attribute("src")
        except Exception:
            src = None

        if src:
            return src
    return None


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    concat_segments = []
    for index, segment in enumerate(parts):
        if segment:
            concat_segments.append(f"'{segment}'")
        if index != len(parts) - 1:
            concat_segments.append('"\'"')
    return "concat(" + ", ".join(concat_segments) + ")"


def get_card_identifier(card):
    try:
        identifier = card.evaluate('el => el.querySelector("img")?.src || null')
        if identifier:
            identifier = str(identifier)
            slash_index = identifier.rfind("/")
            if slash_index != -1 and slash_index + 1 < len(identifier):
                name = identifier[slash_index + 1:]
                question_index = name.find("?")
                if question_index != -1:
                    name = name[:question_index]
                if name:
                    return name
            return identifier
    except Exception:
        print(t("card_identifier_error"))
    return "No ID"


def find_card_by_identifier(page, target_identifier: str):
    literal = xpath_literal(target_identifier)
    img_locator = page.locator(f"//div[contains(@class,'group/media-post-masonry-card')]//img[contains(@src, {literal})]")
    if img_locator.count() == 0:
        return None
    return img_locator.first.locator("xpath=ancestor::div[contains(@class,'group/media-post-masonry-card')]").first
