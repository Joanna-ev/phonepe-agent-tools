"""say_en / say_hi: exact wording for the key cases, and a consistency check that every
amount, date, time and reference spoken in a sentence comes from the result's own fields."""

import json
import re
from datetime import date, datetime, timedelta

import pytest

import say
import spoken
import tools

MONTHS = r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b"
MONEY_WORDS = r"\b(?:rupees?|rupaye|rupaya|paise|paisay|paisa)\b"
DIGIT_WORDS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
    "hi": ["shunya", "ek", "do", "teen", "chaar", "paanch", "chhah", "saat", "aath", "nau"],
}


def call(name, **args):
    out = tools.call_tool(name, args)
    assert "error" not in out, out
    return out


def tomorrow():
    return tools.today_ist() + timedelta(days=1)


# ---------------------------------------------------------------- consistency checker

def assert_say_consistent(r: dict):
    """Every amount/date/time/reference in say_en and say_hi is one of r's own spoken values."""
    for lang in ("en", "hi"):
        text = r[f"say_{lang}"]
        assert not re.search(r"\d", text), f"raw digits in {text!r}"

        # Remove all of r's own spoken phrases; nothing money- or date-like may remain.
        residue = text
        own = sorted((v for k, v in r.items() if k.endswith(f"_spoken_{lang}") and isinstance(v, str)), key=len, reverse=True)
        for phrase in own:
            residue = residue.replace(phrase, " ")
        assert not re.search(MONEY_WORDS, residue, re.I), f"unexplained amount in {text!r}"
        assert not re.search(MONTHS, residue), f"unexplained date in {text!r}"

        # Any run of spoken digits must be the digits of one of r's *_id fields.
        ids = {getattr(spoken, f"digits_{lang}")(v) for k, v in r.items() if k.endswith("_id") and isinstance(v, str)}
        words = "|".join(DIGIT_WORDS[lang])
        for run in re.findall(rf"\b(?:(?:{words}), )+(?:{words})\b", text):
            assert run in ids, f"reference {run!r} not in {ids} for {text!r}"


# Money fields each sentence is expected to state (by action/status); others may be omitted.
_MONEY_SAID = {
    "switch_to_zero_rental": {"one_time_fee_inr", "new_monthly_fee_inr", "monthly_saving_inr"},
    "quote": {"cancellation_fee_inr"},
    "cancellation_confirmed": set(),
}


def all_say_results():
    out = []
    for mid in ("M1001", "M1002", "M1003"):
        out.append(call("run_device_diagnostics", merchant_id=mid))
        for reason in tools.RULES["reason_codes"]:
            out.extend(call("check_retention_options", merchant_id=mid, reason_code=reason)["offers"])
        out.append(call("process_cancellation", merchant_id=mid, confirm=False))
        out.append(call("process_cancellation", merchant_id=mid, confirm=True))
        for action in ("remote_troubleshoot", "free_replacement", "change_language"):
            out.append(call("apply_retention_action", merchant_id=mid, action=action))
        out.append(call("apply_retention_action", merchant_id=mid, action="change_language", language="Tamil"))
        out.append(call("schedule_callback", merchant_id=mid, time="tomorrow 11 AM"))
        out.append(call("schedule_callback", merchant_id=mid, time="Monday 3:30 pm", escalation=True))
        out.append(call("schedule_callback", merchant_id=mid, time="as soon as possible"))
    out.append(call("apply_retention_action", merchant_id="M1001", action="switch_to_zero_rental"))
    out.append(call("apply_retention_action", merchant_id="M1002", action="switch_to_zero_rental"))
    out.append(call("schedule_callback", merchant_id="UNKNOWN", time="tomorrow 6 pm"))
    return out


def test_every_sentence_matches_its_fields():
    results = all_say_results()
    assert len(results) > 40
    for r in results:
        assert "say_en" in r and "say_hi" in r, r
        assert_say_consistent(r)


def test_every_money_and_date_field_is_spoken_where_expected():
    for r in all_say_results():
        key = r.get("action") if "request_id" in r or "break_even_months" in r else r.get("status")
        expected = _MONEY_SAID.get(key, set())
        assert expected <= r.keys() | {"monthly_saving_inr"}, (expected, r)  # saving is on the offer only
        for field in expected & r.keys():
            if r[field] == 0:
                assert "no cancellation fee" in r["say_en"] and "Koi cancellation fee nahi" in r["say_hi"]
                assert not re.search(MONEY_WORDS, r["say_en"]) and not re.search(MONEY_WORDS, r["say_hi"])
                continue
            assert r[f"{field}_spoken_en"] in r["say_en"], (field, r["say_en"])
            assert r[f"{field}_spoken_hi"] in r["say_hi"], (field, r["say_hi"])
        if "pickup_date" in r:
            assert r["pickup_date_spoken_en"] in r["say_en"]
            assert r["pickup_date_spoken_hi"] in r["say_hi"]
        if r.get("callback_date"):
            assert r["callback_date_spoken_en"] in r["say_en"]
            assert r["callback_date_spoken_hi"] in r["say_hi"]
        if r.get("callback_clock"):
            assert r["callback_clock_spoken_en"] in r["say_en"]
            assert r["callback_clock_spoken_hi"] in r["say_hi"]


def test_checker_catches_a_wrong_amount():
    r = call("process_cancellation", merchant_id="M1001", confirm=False)
    bad = {**r, "say_en": r["say_en"].replace("one rupee", "five rupees")}
    with pytest.raises(AssertionError):
        assert_say_consistent(bad)


def test_checker_catches_a_wrong_date():
    r = call("process_cancellation", merchant_id="M1001", confirm=False)
    bad = {**r, "say_hi": r["say_hi"].replace(r["pickup_date_spoken_hi"], "ek January")}
    with pytest.raises(AssertionError):
        assert_say_consistent(bad)


def test_checker_catches_a_wrong_reference():
    r = call("process_cancellation", merchant_id="M1001", confirm=True)
    bad = {**r, "say_en": r["say_en"].replace("one, zero, zero, one", "one, zero, zero, two")}
    with pytest.raises(AssertionError):
        assert_say_consistent(bad)


# ---------------------------------------------------------------- process_cancellation

def test_quote_sentence():
    r = call("process_cancellation", merchant_id="M1001", confirm=False)
    d = spoken.date_en(tools.today_ist() + timedelta(days=3))
    assert r["say_en"] == (
        "The cancellation fee is one rupee. The speaker and charging adapter will be collected "
        f"from your registered store address on {d}."
    )
    assert r["say_hi"].startswith("Cancellation fee ek rupaya hai. Speaker aur charging adapter")


def test_quote_sentence_zero_fee():
    r = call("process_cancellation", merchant_id="M1003", confirm=False)
    assert r["say_en"].startswith("There is no cancellation fee.")
    assert r["say_hi"].startswith("Koi cancellation fee nahi hai.")


def test_confirmed_sentence():
    r = call("process_cancellation", merchant_id="M1002", confirm=True)
    d = tools.today_ist() + timedelta(days=3)
    assert r["say_en"] == (
        "Your cancellation is confirmed. Your cancellation reference is one, zero, zero, one. "
        f"Pickup is on {spoken.date_en(d)}."
    )
    assert r["say_hi"] == (
        "Aapka cancellation confirm ho gaya hai. Aapka cancellation reference number ek, shunya, shunya, ek hai. "
        f"Pickup {spoken.date_hi(d)} ko hoga."
    )


# ---------------------------------------------------------------- apply_retention_action

def test_apply_zero_rental_sentence():
    r = call("apply_retention_action", merchant_id="M1001", action="switch_to_zero_rental")
    assert r["say_en"] == (
        "You are now on the zero rental plan. A one-time fee of nine hundred ninety-nine rupees applies, "
        "and from your next billing cycle you will pay twenty-five rupees a month. "
        "Your request reference is one, zero, zero, one."
    )
    assert r["say_hi"] == (
        "Aapka plan ab zero rental plan hai. Ek baar ki fee nau sau ninyanve rupaye lagegi, aur agle billing "
        "cycle se aap har mahine pachchees rupaye denge. Aapka request reference number ek, shunya, shunya, ek hai."
    )


@pytest.mark.parametrize("action, en_part, hi_part", [
    ("remote_troubleshoot", "within two minutes", "do minute ke andar"),
    ("free_replacement", "within forty-eight hours", "artalees ghante ke andar"),
    ("change_language", "within one hour", "ek ghante ke andar"),
])
def test_apply_says_when(action, en_part, hi_part):
    r = call("apply_retention_action", merchant_id="M1002", action=action)
    assert en_part in r["say_en"] and hi_part in r["say_hi"]
    assert r["say_en"].endswith("Your request reference is one, zero, zero, one.")
    assert r["say_hi"].endswith("Aapka request reference number ek, shunya, shunya, ek hai.")


def test_apply_change_language_names_language():
    r = call("apply_retention_action", merchant_id="M1001", action="change_language", language="Tamil")
    assert r["new_language"] == "Tamil"
    assert "change to Tamil" in r["say_en"] and "Tamil ho jayegi" in r["say_hi"]


def test_apply_retry_returns_same_reference(temp_retention_actions):
    first = call("apply_retention_action", merchant_id="M1001", action="remote_troubleshoot")
    again = call("apply_retention_action", merchant_id="M1001", action="remote_troubleshoot")
    other = call("apply_retention_action", merchant_id="M1001", action="free_replacement")
    assert first["request_id"] == again["request_id"] == "RA-1001"
    assert other["request_id"] == "RA-1002"
    assert len(json.loads(temp_retention_actions.read_text(encoding="utf-8"))) == 2


# ---------------------------------------------------------------- check_retention_options

def test_one_sentence_per_offer():
    r = call("check_retention_options", merchant_id="M1002", reason_code="NOT_WORKING")
    assert [o["say_en"] for o in r["offers"]] == [
        "We can restart your speaker remotely right now, which fixes most problems.",
        "If that does not fix it, we will send you a free replacement speaker within forty-eight hours.",
    ]
    for o in r["offers"]:
        assert o["say_en"].count(".") == 1 and o["say_hi"].count(".") == 1


def test_no_offers_no_sentences():
    r = call("check_retention_options", merchant_id="M1001", reason_code="CLOSING_OR_MOVING")
    assert r["offers"] == [] and "say_en" not in r


# ---------------------------------------------------------------- run_device_diagnostics

def test_diagnostics_offline_sentence():
    r = call("run_device_diagnostics", merchant_id="M1002")
    assert r["say_en"] == (
        "Your speaker's battery is almost empty and the network signal is weak, so it has gone offline."
    )
    assert r["say_hi"] == (
        "Aapke speaker ki battery lagbhag khatam hai aur network signal kamzor hai, isliye woh offline ho gaya hai."
    )


def test_diagnostics_healthy_sentence():
    r = call("run_device_diagnostics", merchant_id="M1001")
    assert r["say_en"] == "Your speaker is working normally, with seventy-eight percent battery and a good network signal."
    assert "athattar percent" in r["say_hi"]


@pytest.mark.parametrize("issues, status, en, hi", [
    ([say.ISSUE_WEAK_SIGNAL], "offline", "Your speaker's network signal is weak, so it has gone offline.",
     "Aapke speaker ka network signal kamzor hai, isliye woh offline ho gaya hai."),
    ([say.ISSUE_LOW_BATTERY], "healthy", "Your speaker's battery is almost empty.",
     "Aapke speaker ki battery lagbhag khatam hai."),
    ([], "offline", "Your speaker has gone offline.", "Aapka speaker offline ho gaya hai."),
])
def test_diagnostics_other_findings(issues, status, en, hi):
    r = say.diagnostics({"healthy": False, "issues": issues, "device_status": status, "signal": "weak"})
    assert (r["say_en"], r["say_hi"]) == (en, hi)


# ---------------------------------------------------------------- schedule_callback

def test_callback_sentence_with_day_and_time():
    r = call("schedule_callback", merchant_id="M1001", time="tomorrow 11 AM")
    d = tomorrow()
    assert r["callback_date"] == d.isoformat() and r["callback_clock"] == "11:00"
    assert r["say_en"] == (
        f"Our team will call you on {spoken.weekday_en(d)}, {spoken.date_en(d)}, at eleven a.m. "
        "Your callback ticket number is one, zero, zero, one."
    )
    assert r["say_hi"] == (
        f"Hamari team aapko {spoken.weekday_hi(d)}, {spoken.date_hi(d)} ko subah gyarah baje call karegi. "
        "Aapka callback ticket number ek, shunya, shunya, ek hai."
    )


def test_callback_escalated_sentence():
    r = call("schedule_callback", merchant_id="M1002", time="tomorrow 4:30 pm", escalation=True)
    assert r["say_en"].startswith("A senior specialist will call you on ")
    assert "at four thirty p.m." in r["say_en"]
    assert r["say_hi"].startswith("Hamare senior specialist aapko ")
    assert "shaam chaar baj kar tees minute call karenge." in r["say_hi"]


def test_callback_weekday_matches_date():
    r = call("schedule_callback", merchant_id="M1001", time="Friday 10 am")
    d = date.fromisoformat(r["callback_date"])
    assert d.weekday() == 4
    assert r["say_en"].startswith(f"Our team will call you on Friday, {spoken.date_en(d)}")


def test_callback_unparsed_time_falls_back_to_raw_text():
    r = call("schedule_callback", merchant_id="M1001", time="as soon as possible")
    assert r["callback_date"] is None and r["callback_clock"] is None
    assert r["say_en"] == (
        "Our team will call you back at the time you asked for: as soon as possible. "
        "Your callback ticket number is one, zero, zero, one."
    )


def test_callback_in_the_past_is_rejected(temp_tickets):
    yesterday = (tools.today_ist() - timedelta(days=1)).isoformat()
    out = tools.call_tool("schedule_callback", {"merchant_id": "M1001", "time": f"{yesterday}T10:00"})
    assert "already passed" in out["error"]
    assert not temp_tickets.exists()


def test_callback_iso_time():
    d = tomorrow()
    r = call("schedule_callback", merchant_id="M1001", time=f"{d.isoformat()}T15:00:00+05:30")
    assert r["callback_date"] == d.isoformat() and r["callback_clock"] == "15:00"
    assert "at three p.m." in r["say_en"] and "dopahar teen baje" in r["say_hi"]


def test_say_failure_keeps_result(monkeypatch):
    def boom(*_):
        raise RuntimeError("bug")
    monkeypatch.setattr(say, "add_say", boom)
    out = tools.call_tool("run_device_diagnostics", {"merchant_id": "M1002"})
    assert out["device_status"] == "offline" and "say_en" not in out
    assert out["battery_percent_spoken_en"] == "four percent"  # spoken fields still there


def test_now_is_ist():
    assert datetime.now(tools.IST).utcoffset() == timedelta(hours=5, minutes=30)
