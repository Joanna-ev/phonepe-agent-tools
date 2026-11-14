"""Speakable English and romanised-Hindi versions of numbers, money, dates and IDs.

add_spoken() walks a tool result and adds spoken fields next to the numeric ones,
chosen by field name:
    *_inr                   -> <field>_spoken_en / <field>_spoken_hi   (rupees)
    cost_per_payment_paise  -> <field>_spoken_en / <field>_spoken_hi   ("about thirty paisay per payment")
    *_months                -> <field>_spoken_en / <field>_spoken_hi   ("ten months" / "das mahine")
    payments_*              -> <field>_spoken_en / <field>_spoken_hi   ("four hundred ten payments")
    *_hours, *_minutes      -> <field>_spoken_en / <field>_spoken_hi   ("forty-eight hours" / "artalees ghante")
    *_clock ("HH:MM")       -> <field>_spoken_en / <field>_spoken_hi   ("eleven a.m." / "subah gyarah baje")
    *_percent               -> <field>_spoken_en / <field>_spoken_hi
    *_date (ISO string)     -> <field>_spoken_en / <field>_spoken_hi   ("the sixteenth of November")
    *_id (with digits)      -> <field>_spoken                          ("callback ticket one, zero, four, two")
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
_REFERENCE_KINDS = {
    "ticket_id": "callback ticket",
    "cancellation_id": "cancellation reference",
    "merchant_id": "merchant number",
    "request_id": "request reference",
}


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
    # 'paisay' so English TTS voices don't say "paze"; the Hindi field keeps 'paise'.
    return f"about {number_en(n)} {'paisa' if n == 1 else 'paisay'} per payment"


def paise_per_payment_hi(n: int) -> str:
    return f"har payment par lagbhag {number_hi(n)} {'paisa' if n == 1 else 'paise'}"


def months_en(n: int) -> str:
    return f"{number_en(n)} {'month' if n == 1 else 'months'}"


def months_hi(n: int) -> str:
    return f"{number_hi(n)} {'mahina' if n == 1 else 'mahine'}"


def payments_en(n: int) -> str:
    return f"{number_en(n)} {'payment' if n == 1 else 'payments'}"


def payments_hi(n: int) -> str:
    return f"{number_hi(n)} {'payment' if n == 1 else 'payments'}"


def hours_en(n: int) -> str:
    return f"{number_en(n)} {'hour' if n == 1 else 'hours'}"


def hours_hi(n: int) -> str:
    return f"{number_hi(n)} {'ghanta' if n == 1 else 'ghante'}"


def minutes_en(n: int) -> str:
    return f"{number_en(n)} {'minute' if n == 1 else 'minutes'}"


def minutes_hi(n: int) -> str:
    return f"{number_hi(n)} minute"


def _parse_clock(hhmm: str) -> tuple[int, int]:
    hour, minute = (int(p) for p in hhmm.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"bad clock time {hhmm!r}")
    return hour, minute


def clock_en(hhmm: str) -> str:
    """'11:00' -> 'eleven a.m.', '15:30' -> 'three thirty p.m.', '09:05' -> 'nine oh five a.m.'."""
    hour, minute = _parse_clock(hhmm)
    words = number_en(hour % 12 or 12)
    if minute:
        words += f" {'oh ' if minute < 10 else ''}{number_en(minute)}"
    return f"{words} {'a.m.' if hour < 12 else 'p.m.'}"


def clock_hi(hhmm: str) -> str:
    """'11:00' -> 'subah gyarah baje', '15:30' -> 'dopahar teen baj kar tees minute'."""
    hour, minute = _parse_clock(hhmm)
    if 4 <= hour < 12:
        period = "subah"
    elif 12 <= hour < 16:
        period = "dopahar"
    elif 16 <= hour < 20:
        period = "shaam"
    else:
        period = "raat"
    h = number_hi(hour % 12 or 12)
    return f"{period} {h} baj kar {number_hi(minute)} minute" if minute else f"{period} {h} baje"


_WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_WEEKDAYS_HI = ["Somvaar", "Mangalvaar", "Budhvaar", "Guruvaar", "Shukravaar", "Shanivaar", "Ravivaar"]


def weekday_en(d: date) -> str:
    return _WEEKDAYS_EN[d.weekday()]


def weekday_hi(d: date) -> str:
    return _WEEKDAYS_HI[d.weekday()]


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


def reference(ref: str, kind: str = "reference number") -> str:
    """('CB-1042', 'callback ticket') -> 'callback ticket one, zero, four, two'.

    Letters are dropped (the kind word says what the number is); digits are read one by one.
    """
    return f"{kind} {digits_en(ref)}"


def digits_en(ref: str) -> str:
    """'CN-1001' -> 'one, zero, zero, one'."""
    return ", ".join(_ONES_EN[int(c)] for c in re.findall(r"\d", ref))


def digits_hi(ref: str) -> str:
    """'CN-1001' -> 'ek, shunya, shunya, ek'."""
    return ", ".join(_HI[int(c)] for c in re.findall(r"\d", ref))


def plan_name(plan: str) -> str:
    return _PLAN_NAMES.get(plan, f"{plan.replace('_', ' ')} plan")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _spoken_fields(key: str, value: Any) -> dict:
    if key == "cost_per_payment_paise" and _is_int(value):
        return {f"{key}_spoken_en": paise_per_payment_en(value), f"{key}_spoken_hi": paise_per_payment_hi(value)}
    if key.endswith("_inr") and _is_int(value):
        return {f"{key}_spoken_en": rupees_en(value), f"{key}_spoken_hi": rupees_hi(value)}
    if key.endswith("_months") and _is_int(value):
        return {f"{key}_spoken_en": months_en(value), f"{key}_spoken_hi": months_hi(value)}
    if key.startswith("payments_") and _is_int(value):
        return {f"{key}_spoken_en": payments_en(value), f"{key}_spoken_hi": payments_hi(value)}
    if key.endswith("_hours") and _is_int(value):
        return {f"{key}_spoken_en": hours_en(value), f"{key}_spoken_hi": hours_hi(value)}
    if key.endswith("_minutes") and _is_int(value):
        return {f"{key}_spoken_en": minutes_en(value), f"{key}_spoken_hi": minutes_hi(value)}
    if key.endswith("_clock") and isinstance(value, str):
        return {f"{key}_spoken_en": clock_en(value), f"{key}_spoken_hi": clock_hi(value)}
    if key.endswith("_percent") and _is_int(value):
        return {f"{key}_spoken_en": percent_en(value), f"{key}_spoken_hi": percent_hi(value)}
    if key.endswith("_date") and isinstance(value, str):
        d = date.fromisoformat(value)
        return {f"{key}_spoken_en": date_en(d), f"{key}_spoken_hi": date_hi(d)}
    if key.endswith("_id") and isinstance(value, str) and re.search(r"\d", value):
        return {f"{key}_spoken": reference(value, _REFERENCE_KINDS.get(key, "reference number"))}
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
