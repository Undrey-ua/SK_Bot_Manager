from __future__ import annotations

import re

_TRANSLIT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "ie",
    "ж": "zh",
    "з": "z",
    "и": "y",
    "і": "i",
    "ї": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ь": "",
    "ю": "iu",
    "я": "ia",
}


def slug_visit_task_code(label: str) -> str:
    parts: list[str] = []
    for ch in label.strip().lower():
        if ch in _TRANSLIT:
            parts.append(_TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            parts.append(ch)
    text = "".join(parts)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or "task")[:50]
