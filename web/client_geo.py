from __future__ import annotations

import re

from database.models import Client


_STREET_HINT_RE = re.compile(
    r"(^|\b)(вул\.?|улиц[яы]|просп\.?|пр-т|пров\.?|провулок|бул\.?|б-р\.?|бульвар|пл\.?|площа|наб\.?|набережна|шосе|дорога|квартал|мкр\.?|мікрорайон|жк|буд\.?|будинок|д\.)\b",
    re.IGNORECASE,
)

_STREET_NAME_RE = re.compile(
    r"(ського|ого|ова|ева|ина|енка|ська)$",
    re.IGNORECASE,
)

_CITY_RE = re.compile(
    r"(^|\b)(м\.?\s*)?(київ|киев|kiev|львів|львов|lviv|харків|харьков|kharkiv|дніпро|днепр|dnipro|одеса|одесса|odesa|житомир|вінниця|полтава|чернігів|черкаси|хмельницький|івано-?франківськ|ивано-?франковск|тернопіль|луцьк|рівне|кропивницький|суми|миколаїв|николаев|херсон|запоріжжя|запорожье|ужгород|чернівці)\b",
    re.IGNORECASE,
)

_OBLAST_SUFFIX_RE = re.compile(r"(ська|ський)(\s+область)?$", re.IGNORECASE)

_CITY_PREFIX_RE = re.compile(r"^\s*місто\s*:", re.IGNORECASE)


def _normalize_city(raw: str) -> str:
    city = raw.strip()
    city = re.sub(r"^(м\.?\s*)", "", city, flags=re.IGNORECASE).strip()
    return city


def _looks_like_oblast(text: str) -> bool:
    return bool(_OBLAST_SUFFIX_RE.search(text.strip()))


def _looks_like_street(text: str) -> bool:
    chunk = text.strip()
    if not chunk:
        return True
    if _STREET_HINT_RE.search(chunk):
        return True
    if any(ch.isdigit() for ch in chunk):
        return True
    if _STREET_NAME_RE.search(chunk) and not _CITY_RE.search(chunk):
        return True
    return False


_CITY_IN_NAME_RE = re.compile(r"\(([^)]+)\)")


def _city_from_name(name: str | None) -> str | None:
    if not name:
        return None
    for match in _CITY_IN_NAME_RE.finditer(name):
        candidate = _normalize_city(match.group(1))
        if candidate and _is_valid_city(candidate):
            return candidate
    return None


def _is_valid_city(text: str) -> bool:
    chunk = text.strip()
    if not chunk:
        return False
    if _looks_like_oblast(chunk):
        return False
    if _looks_like_street(chunk):
        return False
    return True


def _city_from_comment(comment: str | None) -> str | None:
    if not comment:
        return None
    text = comment.strip()
    if not _CITY_PREFIX_RE.match(text):
        return None
    return text.split(":", 1)[1].strip() or None


def client_stored_city(client: Client) -> str | None:
    raw = getattr(client, "city", None)
    if raw and str(raw).strip():
        return str(raw).strip()
    return _city_from_comment(client.comment)


def client_display_comment(client: Client) -> str:
    """Коментар для UI без рядка «Місто: …» (legacy імпорт)."""
    if not client.comment:
        return "—"
    lines = client.comment.strip().splitlines()
    kept: list[str] = []
    for line in lines:
        if _CITY_PREFIX_RE.match(line.strip()):
            continue
        kept.append(line)
    text = "\n".join(kept).strip()
    return text or "—"


def client_display_city(client: Client) -> str:
    city = client_city(client)
    return city if city != "—" else "—"


def _city_from_address_and_region(client: Client) -> str | None:
    address = (client.address or "").strip()
    parts = [p.strip() for p in address.split(",") if p.strip()] if address else []

    for part in parts:
        match = _CITY_RE.search(part)
        if not match:
            continue
        city = _normalize_city(match.group(0))
        if city and _is_valid_city(city):
            return city

    region = getattr(client, "region", None)
    region_name = str(region.name).strip() if region and region.name else ""
    if region_name and not _looks_like_oblast(region_name) and _CITY_RE.search(region_name):
        city = _normalize_city(region_name)
        if city and _is_valid_city(city):
            return city

    return None


def client_city(client: Client) -> str:
    stored = client_stored_city(client)
    if stored and _is_valid_city(stored):
        return _normalize_city(stored)

    parsed = _city_from_address_and_region(client)
    if parsed:
        return parsed

    from_name = _city_from_name(client.name)
    return from_name if from_name else "—"


def client_oblast(client: Client) -> str:
    if client.region:
        return client.region.name
    return "—"
