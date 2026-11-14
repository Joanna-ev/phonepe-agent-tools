"""Speakable English and romanised-Hindi versions of numbers, money, dates and IDs.

add_spoken() walks a tool result and adds spoken fields next to the numeric ones,
chosen by field name:
    *_inr                   -> <field>_spoken_en / <field>_spoken_hi   (rupees)
    cost_per_payment_paise  -> <field>_spoken_en / <field>_spoken_hi   ("about thirty paise per payment")
    *_percent               -> <field>_spoken_en / <field>_spoken_hi
    *_date (ISO string)     -> <field>_spoken_en / <field>_spoken_hi   ("the sixteenth of November")
    *_id (with digits)      -> <field>_spoken                          ("C B, one zero four two")
    plan                    -> plan_name_spoken                        ("zero rental plan")

Numbers use the Indian scale (hazaar, lakh, karod) and are supported below 100 crore.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_ONES_EN = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_TENS_EN = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# Hindi numbers 0-99 are irregular, so they are listed in full (romanised).
_HI = [
    "shunya", "ek", "do", "teen", "chaar", "paanch", "chhah", "saat", "aath", "nau",
    "das", "gyarah", "barah", "terah", "chaudah", "pandrah", "solah", "satrah", "atharah", "unnees",
    "bees", "ikkees", "bais", "teis", "chaubees", "pachchees", "chhabbees", "sattais", "atthais", "untees",
    "tees", "iktees", "battees", "taintees", "chauntees", "paintees", "chhattees", "saintees", "artees", "untalees",
    "chalees", "iktalees", "bayalees", "taintalees", "chavalees", "paintalees", "chhiyalees", "saintalees", "artalees", "unchas",
    "pachaas", "ikyavan", "bavan", "tirpan", "chauvan", "pachpan", "chhappan", "sattavan", "athavan", "unsath",
    "saath", "iksath", "basath", "tirsath", "chausath", "painsath", "chhiyasath", "sarsath", "arsath", "unhattar",
    "sattar", "ikhattar", "bahattar", "tihattar", "chauhattar", "pachhattar", "chhihattar", "satattar", "athattar", "unasi",
    "assi", "ikyasi", "bayasi", "tirasi", "chaurasi", "pachasi", "chhiyasi", "sattasi", "athasi", "navasi",
    "nabbe", "ikyanve", "banve", "tiranve", "chauranve", "pachanve", "chhiyanve", "sattanve", "atthanve", "ninyanve",
]
assert len(_HI) == 100

# (value, English word, Hindi word), largest first. Every multiplier stays below 100.
_SCALES = [(10**7, "crore", "karod"), (10**5, "lakh", "lakh"), (1000, "thousand", "hazaar"), (100, "hundred", "sau")]
_LIMIT = 10**9

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_ORDINAL_IRREGULAR = {
    "one": "first", "two": "second", "three": "third", "five": "fifth",
    "eight": "eighth", "nine": "ninth", "twelve": "twelfth",
}
_PLAN_NAMES = {"monthly": "monthly plan", "zero_rental": "zero rental plan"}


def _below_100_en(n: int) -> str:
    if n < 20:
        return _ONES_EN[n]
    tens, ones = divmod(n, 10)
    return _TENS_EN[tens] + (f"-{_ONES_EN[ones]}" if ones else "")


def _words(n: int, lang: str) -> str:
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < _LIMIT:
        raise ValueError(f"cannot speak {n!r}; whole numbers from 0 to {_LIMIT - 1} only")
    below_100 = _below_100_en if lang == "en" else _HI.__getitem__
    if n == 0:
        return below_100(0)
    parts = []
    for value, en, hi in _SCALES:
        count, n = divmod(n, value)
        if count:
            parts.append(f"{below_100(count)} {en if lang == 'en' else hi}")
    if n:
        parts.append(below_100(n))
    return " ".join(parts)


def number_en(n: int) -> str:
    """999 -> 'nine hundred ninety-nine'."""
    return _words(n, "en")


def number_hi(n: int) -> str:
    """999 -> 'nau sau ninyanve'."""
    return _words(n, "hi")


def ordinal_en(n: int) -> str:
    """16 -> 'sixteenth', 21 -> 'twenty-first'."""
    head, last = re.match(r"(.*?)([a-z]+)$", number_en(n)).groups()
    if last in _ORDINAL_IRREGULAR:
        last = _ORDINAL_IRREGULAR[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return head + last


def rupees_en(n: int) -> str:
    return f"{number_en(n)} {'rupee' if n == 1 else 'rupees'}"


def rupees_hi(n: int) -> str:
    return f"{number_hi(n)} {'rupaya' if n == 1 else 'rupaye'}"


def paise_per_payment_en(n: int) -> str:
    return f"about {number_en(n)} {'paisa' if n == 1 else 'paise'} per payment"


def paise_per_payment_hi(n: int) -> str:
    return f"har payment par lagbhag {number_hi(n)} {'paisa' if n == 1 else 'paise'}"


def percent_en(n: int) -> str:
    return f"{number_en(n)} percent"


def percent_hi(n: int) -> str:
    return f"{number_hi(n)} percent"


def date_en(d: date) -> str:
    """date(2026, 11, 16) -> 'the sixteenth of November'."""
    return f"the {ordinal_en(d.day)} of {_MONTHS[d.month - 1]}"


def date_hi(d: date) -> str:
    """date(2026, 11, 16) -> 'solah November'."""
    return f"{number_hi(d.day)} {_MONTHS[d.month - 1]}"


def reference(ref: str) -> str:
    """'CB-1042' -> 'C B, one zero four two'; letters spelled out, digits read one by one."""
    groups = re.findall(r"[A-Za-z]+|\d+", ref)
    return ", ".join(
        " ".join(_ONES_EN[int(c)] for c in g) if g.isdigit() else " ".join(g.upper())
        for g in groups
    )


def plan_name(plan: str) -> str:
    return _PLAN_NAMES.get(plan, f"{plan.replace('_', ' ')} plan")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _spoken_fields(key: str, value: Any) -> dict:
    if key == "cost_per_payment_paise" and _is_int(value):
        return {f"{key}_spoken_en": paise_per_payment_en(value), f"{key}_spoken_hi": paise_per_payment_hi(value)}
    if key.endswith("_inr") and _is_int(value):
        return {f"{key}_spoken_en": rupees_en(value), f"{key}_spoken_hi": rupees_hi(value)}
    if key.endswith("_percent") and _is_int(value):
        return {f"{key}_spoken_en": percent_en(value), f"{key}_spoken_hi": percent_hi(value)}
    if key.endswith("_date") and isinstance(value, str):
        d = date.fromisoformat(value)
        return {f"{key}_spoken_en": date_en(d), f"{key}_spoken_hi": date_hi(d)}
    if key.endswith("_id") and isinstance(value, str) and re.search(r"\d", value):
        return {f"{key}_spoken": reference(value)}
    if key == "plan" and isinstance(value, str):
        return {"plan_name_spoken": plan_name(value)}
    return {}


def add_spoken(obj: Any) -> Any:
    """Return a copy of obj with spoken fields inserted right after each matching field."""
    if isinstance(obj, list):
        return [add_spoken(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for key, value in obj.items():
        out[key] = add_spoken(value)
        out.update(_spoken_fields(key, value))
    return out
