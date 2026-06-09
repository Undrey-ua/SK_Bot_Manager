"""Зіставлення назв стендів і торгових марок (як у матриці продажів)."""

from __future__ import annotations


def norm_text(value: str) -> str:
    return (
        str(value or "")
        .strip()
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("`", "'")
    )


def stand_tokens_comparable(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return " ".join(norm_text(s).split()).lower()

    x = norm(a)
    y = norm(b)
    if not x or not y:
        return False
    if x == y:
        return True

    def tail(s: str) -> str:
        i = s.rfind(":")
        return s if i < 0 else s[i + 1 :].strip()

    tx = tail(x)
    ty = tail(y)
    return tx == y or x == ty or ty == x or y == tx or (tx and ty and tx == ty)


def is_big_product_line(normalized: str) -> bool:
    t = norm_text(normalized)
    return t in {
        "BIG: Carmelita",
        "BIG: Pureloc40",
        "BIG: Novocore Legacy",
        "BIG (невизначено)",
        "BIG",
    }


def matrix_col_key_from_name(name: str) -> str:
    b = norm_text(name)
    if b.upper() == "BIG":
        return "BIG"
    if b.startswith("BIG:"):
        return "BIG"
    if is_big_product_line(b):
        return "BIG"
    return b


def matrix_col_keys_match(sale_col_key: str, header_col_key: str) -> bool:
    a = norm_text(sale_col_key)
    b = norm_text(header_col_key)
    if not a or not b:
        return False
    if a == b or a.lower() == b.lower():
        return True
    if a == "BIG" and b == "BIG":
        return True
    if a == "BIG" or b == "BIG":
        other = b if a == "BIG" else a
        if other == "BIG":
            return True
        return is_big_product_line(other) or other.startswith("BIG:")
    return stand_tokens_comparable(a, b)


def stand_matches_brand(stand_name: str, brand_name: str) -> bool:
    s = matrix_col_key_from_name(stand_name)
    return matrix_col_keys_match(s, brand_name) or matrix_col_keys_match(
        s, matrix_col_key_from_name(brand_name)
    )
