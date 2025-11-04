from __future__ import annotations

from .localization import t


def load_cookie_header(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        data = handle.read().strip()
    if not data:
        raise ValueError(t("empty_cookie_file", path=path))

    valid_pairs = [part for part in data.split(";") if "=" in part]
    if not valid_pairs:
        raise ValueError(t("empty_cookie_file", path=path))
    return data


def cookie_header_to_list(header: str, domain: str):
    cookies = []
    for part in header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain,
                "path": "/",
                "secure": True,
                "sameSite": "None",
            }
        )
    return cookies
