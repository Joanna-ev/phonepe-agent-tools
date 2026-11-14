"""Turn the agent's callback time ("tomorrow 11 AM", "Monday 3:30 pm", ISO) into a date and clock time.

Anything it cannot understand returns (None, None) and the raw text is kept as-is.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_PM_WORDS = r"\b(?:afternoon|evening|night|tonight)\b"
_AM_WORDS = r"\bmorning\b"


def _parse_clock(text: str) -> time | None:
    m = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?\s*m\b\.?", text)
    if m:
        hour, minute, meridiem = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "p" else 0)
    else:
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", text) or re.search(r"\bat\s+(\d{1,2})\b", text)
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.re.groups > 1 else 0
        if 1 <= hour <= 12:
            if re.search(_PM_WORDS, text):
                hour = hour % 12 + 12
            elif re.search(_AM_WORDS, text):
                hour = hour % 12
            elif hour <= 7:
                hour += 12  # "at 5" means 5 p.m. for a business callback; 8-11 stay morning
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def parse_callback_time(text: str, now: datetime) -> tuple[date | None, time | None]:
    """Return (date, clock) for text, relative to `now` (a timezone-aware datetime in IST)."""
    s = str(text or "").strip()
    today = now.date()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s), None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        pass
    else:
        if dt.tzinfo is not None:
            dt = dt.astimezone(now.tzinfo)
        return dt.date(), dt.time().replace(second=0, microsecond=0)

    low = s.lower()
    clock = _parse_clock(low)
    weekday_given = False
    if re.search(r"\bday after tomorrow\b", low):
        day = today + timedelta(days=2)
    elif re.search(r"\btomorrow\b", low):
        day = today + timedelta(days=1)
    elif re.search(r"\b(?:today|tonight)\b", low):
        day = today
    else:
        day = None
        for i, name in enumerate(_WEEKDAYS):
            if re.search(rf"\b{name}\b", low):
                day = today + timedelta(days=(i - today.weekday()) % 7)
                weekday_given = True
                break

    if clock is not None:
        if day is None:  # a bare time means the next time that clock comes round
            day = today if datetime.combine(today, clock, now.tzinfo) > now else today + timedelta(days=1)
        elif weekday_given and datetime.combine(day, clock, now.tzinfo) <= now:
            day += timedelta(days=7)  # "Saturday 9 am" said on Saturday afternoon means next week
    return day, clock
