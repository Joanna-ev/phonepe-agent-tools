from datetime import date, datetime, time, timedelta, timezone

import pytest

from callback_time import parse_callback_time

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 14, 14, 0, tzinfo=IST)  # Saturday 2 p.m.
TODAY = NOW.date()


@pytest.mark.parametrize("text, day, clock", [
    ("tomorrow 11 AM", date(2026, 11, 15), time(11, 0)),
    ("tomorrow at 11am", date(2026, 11, 15), time(11, 0)),
    ("11 a.m. tomorrow", date(2026, 11, 15), time(11, 0)),
    ("Tomorrow 4:30 PM", date(2026, 11, 15), time(16, 30)),
    ("tomorrow 11.30 am", date(2026, 11, 15), time(11, 30)),
    ("day after tomorrow 10 am", date(2026, 11, 16), time(10, 0)),
    ("today 5 pm", TODAY, time(17, 0)),
    ("tonight at 8", TODAY, time(20, 0)),
    ("tomorrow morning at 9", date(2026, 11, 15), time(9, 0)),
    ("tomorrow evening at 6", date(2026, 11, 15), time(18, 0)),
    ("tomorrow at 5", date(2026, 11, 15), time(17, 0)),   # bare 1-7 assumed p.m.
    ("tomorrow at 9", date(2026, 11, 15), time(9, 0)),    # bare 8-11 assumed a.m.
    ("tomorrow 15:00", date(2026, 11, 15), time(15, 0)),
    ("12 pm tomorrow", date(2026, 11, 15), time(12, 0)),
    ("12 am tomorrow", date(2026, 11, 15), time(0, 0)),
    ("Monday 3:30 pm", date(2026, 11, 16), time(15, 30)),
    ("monday", date(2026, 11, 16), None),
    ("Saturday 5 pm", TODAY, time(17, 0)),                 # later today
    ("Saturday 9 am", date(2026, 11, 21), time(9, 0)),     # already passed today -> next week
    ("5 pm", TODAY, time(17, 0)),                          # bare time still ahead -> today
    ("10 am", date(2026, 11, 15), time(10, 0)),            # bare time already passed -> tomorrow
    ("tomorrow", date(2026, 11, 15), None),
    ("2026-11-20", date(2026, 11, 20), None),
    ("2026-11-20T15:45", date(2026, 11, 20), time(15, 45)),
    ("2026-11-20T10:15:00Z", date(2026, 11, 20), time(15, 45)),  # UTC converted to IST
    ("as soon as possible", None, None),
    ("", None, None),
    ("tomorrow 13 pm", date(2026, 11, 15), None),          # invalid clock ignored
    ("on 15 November", None, None),                        # bare number is not a time
])
def test_parse(text, day, clock):
    assert parse_callback_time(text, NOW) == (day, clock)
