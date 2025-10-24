from __future__ import annotations

import os

MORE_OPTIONS_LABELS = ["More options", "További lehetőségek"]
DOWNLOAD_BUTTON_LABELS = ["Download", "Letöltés"]
BACK_BUTTON_LABELS = ["Back", "Vissza"]
UPSCALE_MENU_LABELS = ["Videó felskálázása", "Upscale video"]

MESSAGES = {
    "en": {
        # General messages
        "gallery_opening": "🌐 Opening gallery...",
        "gallery_load_failed": "❌ Failed to load gallery – check your cookie file.",
        "forbidden_error": "❌ 403 Forbidden — cookie may be invalid or browser fingerprint blocked.",
        "forbidden_help": "ℹ️ Try regenerating the cookie file with the same browser and user-agent as the source.",
        "process_interrupted": "❌ Process interrupted:",
        "already_exists_overwrite": "🟡 Already exists ({filename}), overwriting.",
        "zero_byte_file_delete_retry": "⚠️  0-byte file — deleting and trying to download from opened card...",
        "zero_byte_file_delete_failed": "Could not delete 0-byte file: {error}",
        "alternative_download": "🔁 Alternative download: {url}",
        "alternative_download_success": "📥 Downloaded from alternative source: {filename} ({size} bytes)",
        "download_success": "📥 Downloaded: {filename}",
        "back_to_gallery": "↩️  Back to gallery.",
        "back_failed_continue": "⚠️  Could not go back, but continuing.",
        "processing_complete": "🎉 Done – all videos processed.",
        "upscale_warnings": "⚠️  The following videos were downloaded without upscale:",
        "no_upscale_warnings": "✅ All videos were successfully upscaled before download.",
        "download_errors": "❗ Download error list:",
        "no_download_errors": "✅ No download errors occurred.",
        "no_dotenv_warning": "⚠️  python-dotenv package not installed, .env file will not be loaded.",
        "invalid_int_config": "⚠️  Invalid integer in {key} variable, using default value.",
        "card_processing": "🎬 Processing video {index}. ({identifier})...",
        "card_click": "🖱️  Opened...",
        "menu_opened": "📂 Menu opened...",
        "already_upscaled": "🟢 Already upscaled, skipping upscale step.",
        "upscale_start": "🕐 Starting upscale...",
        "upscale_success": "✅ Upscale complete.",
        "upscale_timeout": "⚠️  Upscale timeout – downloading without upscale.",
        "no_download_button": "Download button not found.",
        "card_disappeared_retry": "♻️  Card disappeared, searching again...",
        "card_click_timeout": "Card click timed out",
        "card_not_found": "Card not found for clicking",
        "scrolling": "⬇️  Scrolling down...",
        "scrolling_up": "⬆️  Scrolling up...",
        "no_cards_scroll": "🌀 No cards to process, scrolling further...",
        "remaining_videos": "🔢 Remaining found videos ({count}): {queue}",
        "card_missing_scroll": "🔄 Card not in DOM, scrolling down...",
        "card_search_scroll": "🔎 Searching for card {identifier} with scrolls...",
        "card_not_found_after_scroll": "⚠️  Card {identifier} not found, skipping.",
        "card_not_found_reason": "Card not found after scrolling",
        "already_downloaded_image": "⏭️  Already downloaded image: {path}",
        "already_downloaded_video": "⏭️  Existing video ({width}): {path}",
        "alternative_download_http_error": "Alternative download HTTP error:\n{error}",
        "alternative_download_failed": "Alternative download failed: HTTP {status}",
        "alternative_download_zero_byte": "Alternative download also remained 0-byte",
        "video_src_not_found": "Video URL not found in card DOM",
        "delete_existing_failed": "Could not delete existing file: {error}",
        "card_identifier_error": "❌ Error extracting video identifier.",
        "no_cards_found": "❌ Failed to load gallery – check your cookie file.",
        "video_width_unknown": "unknown",
        "scroll_direction_down": "down",
        "scroll_direction_up": "up",
        "download_error": "❌ Download error: {reason}",
        "ffprobe_not_found": "⚠️  ffprobe not found, cannot check video resolution – will reprocess videos.",
        "empty_cookie_file": "The cookie file is empty!",
        "card_not_found_for_clicking": "Card not found for clicking",
        "card_click_timeout": "Card click timed out",
        "delete_existing_failed": "Could not delete existing file: {error}",
        "video_processing_error": "Error at video {index}:\n{error}",
        "skipping_no_video_option": "⏭️  Skipping {identifier} card – no video option available",
        "no_image_element": "Image element not found in card",
        "no_image_src": "Image URL not found in card",
        "image_download_failed": "Image download failed: HTTP {status}",
        "no_video_option_skip_upscale": "⏭️  No video option – skipping upscale step",
    },
    "hu": {
        # General messages
        "gallery_opening": "🌐 Galéria megnyitása...",
        "gallery_load_failed": "❌ Nem sikerült betölteni a galériát – ellenőrizd a cookie fájlt.",
        "forbidden_error": "❌ 403 Forbidden — valószínűleg a cookie érvénytelen vagy a böngésző fingerprint blokkolt.",
        "forbidden_help": "ℹ️ Próbáld új cookie fájl generálását ugyanazzal a böngészővel és user-agenttel, ahonnan a cookie származik.",
        "process_interrupted": "❌ Folyamat megszakadt:",
        "already_exists_overwrite": "🟡 Már létezik ({filename}), felülírom.",
        "zero_byte_file_delete_retry": "⚠️  0 bájtos fájl — törlöm és megpróbálom a megnyitott kártyából letölteni...",
        "zero_byte_file_delete_failed": "Nem tudtam törölni a 0 bájtos fájlt: {error}",
        "alternative_download": "🔁 Alternatív letöltés: {url}",
        "alternative_download_success": "📥 Letöltve alternatív forrásból: {filename} ({size} bájt)",
        "download_success": "📥 Letöltve: {filename}",
        "back_to_gallery": "↩️  Visszatérés a galériába.",
        "back_failed_continue": "⚠️  Nem sikerült visszalépni, de folytatom.",
        "processing_complete": "🎉 Kész – minden videó feldolgozva.",
        "upscale_warnings": "⚠️  Az alábbi videók upscale nélkül kerültek letöltésre:",
        "no_upscale_warnings": "✅ Minden videó sikeresen upscale-lve lett a letöltés előtt.",
        "download_errors": "❗ Letöltési hibák listája:",
        "no_download_errors": "✅ Nem történt letöltési hiba.",
        "no_dotenv_warning": "⚠️  A python-dotenv csomag nincs telepítve, .env fájl nem kerül betöltésre.",
        "invalid_int_config": "⚠️  Érvénytelen egész szám a(z) {key} változóban, az alapértelmezett értéket használom.",
        "card_processing": "🎬 {index}. ({identifier}) videó feldolgozása...",
        "card_click": "🖱️  Megnyitva...",
        "menu_opened": "📂 Menü megnyitva...",
        "already_upscaled": "🟢 Már upscale-elve van, kihagyom az upscale lépést.",
        "upscale_start": "🕐 Upscale indítása...",
        "upscale_success": "✅ Upscale kész.",
        "upscale_timeout": "⚠️  Upscale időtúllépés – letöltés upscale nélkül.",
        "no_download_button": "Nem találtam Letöltés gombot.",
        "card_disappeared_retry": "♻️  A kártya eltűnt, újrakeresem...",
        "card_click_timeout": "A kártyára kattintás időtúllépett",
        "card_not_found": "A kártya nem található a kattintáshoz",
        "scrolling": "⬇️  Görgetés lefelé...",
        "scrolling_up": "⬆️  Görgetés felfelé...",
        "no_cards_scroll": "🌀 Nincs feldolgozandó kártya, görgetek tovább...",
        "remaining_videos": "🔢 Hátralévő megtalált videók ({count}): {queue}",
        "card_missing_scroll": "🔄 Kártya nincs a DOM-ban, görgetés lefelé...",
        "card_search_scroll": "🔎 {identifier} kártya keresése görgetésekkel...",
        "card_not_found_after_scroll": "⚠️  {identifier} kártya nem található, kihagyás.",
        "card_not_found_reason": "A kártya nem található a görgetések után",
        "already_downloaded_image": "⏭️  Már lementett kép: {path}",
        "already_downloaded_video": "⏭️  Már létező videó ({width}): {path}",
        "alternative_download_http_error": "Alternatív letöltés HTTP hiba:\n{error}",
        "alternative_download_failed": "Alternatív letöltés sikertelen: HTTP {status}",
        "alternative_download_zero_byte": "Alternatív letöltés is 0 bájtos maradt",
        "video_src_not_found": "Nem találtam videó URL-t a kártya DOM-jában",
        "delete_existing_failed": "Nem tudtam törölni a régi fájlt: {error}",
        "card_identifier_error": "❌ Hiba a videó azonosító kinyerésekor.",
        "no_cards_found": "❌ Nem sikerült betölteni a galériát – ellenőrizd a cookie fájlt.",
        "video_width_unknown": "ismeretlen",
        "scroll_direction_down": "lefelé",
        "scroll_direction_up": "felfelé",
        "download_error": "❌ Letöltési hiba: {reason}",
        "ffprobe_not_found": "⚠️  ffprobe nem található, a videók felbontását nem tudom ellenőrizni – újra feldolgozom őket.",
        "empty_cookie_file": "A cookie fájl üres!",
        "card_not_found_for_clicking": "A kártya nem található a kattintáshoz",
        "card_click_timeout": "A kártyára kattintás időtúllépett",
        "delete_existing_failed": "Nem tudtam törölni a régi fájlt: {error}",
        "video_processing_error": "Hiba a(z) {index}. videónál:\n{error}",
        "skipping_no_video_option": "⏭️  {identifier} kártya kihagyása – nincs videó opció",
        "no_image_element": "Nem találtam kép elemet a kártyában",
        "no_image_src": "Nem találtam kép URL-t a kártyában",
        "image_download_failed": "Kép letöltés sikertelen: HTTP {status}",
        "no_video_option_skip_upscale": "⏭️  Nincs videó opció – kihagyom az upscale lépést",
    },
}


def get_message(key: str, **kwargs) -> str:
    """Get localized message by key, with optional formatting."""
    lang = os.getenv("LANGUAGE", "hu")
    if lang not in MESSAGES:
        lang = "hu"  # fallback to Hungarian

    message = MESSAGES[lang].get(key, f"[{key}]")  # fallback to key if not found
    if kwargs:
        try:
            message = message.format(**kwargs)
        except (KeyError, ValueError):
            pass  # keep original message if formatting fails
    return message


def t(key: str, **kwargs) -> str:
    """Alias for get_message for shorter usage."""
    return get_message(key, **kwargs)
