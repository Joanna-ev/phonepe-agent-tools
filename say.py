"""Ready-to-say sentences (say_en / say_hi) for tool results.

Sentences are built only from the finished result, after spoken.add_spoken() has run:
amounts and dates come from the result's own *_spoken_en / *_spoken_hi fields, and
other numbers are converted from the result's numeric fields. So a sentence cannot
quote a figure the result doesn't contain.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

import spoken

# Shared with tools.run_device_diagnostics so the finding sentence follows its checks.
ISSUE_LOW_BATTERY = "battery critically low"
ISSUE_WEAK_SIGNAL = "weak signal"

_SIGNAL_HI = {"good": "achha", "weak": "kamzor"}


def _join_en(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _join_hi(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} aur {items[-1]}"


def _say(en: str, hi: str) -> dict:
    return {"say_en": en, "say_hi": hi}


# ---------------------------------------------------------------- process_cancellation

def cancellation(r: dict) -> dict:
    if r["status"] == "cancellation_confirmed":
        return _say(
            "Your cancellation is confirmed. "
            f"Your cancellation reference is {spoken.digits_en(r['cancellation_id'])}. "
            f"Pickup is on {r['pickup_date_spoken_en']}.",
            "Aapka cancellation confirm ho gaya hai. "
            f"Aapka cancellation reference number {spoken.digits_hi(r['cancellation_id'])} hai. "
            f"Pickup {r['pickup_date_spoken_hi']} ko hoga.",
        )

    if r["cancellation_fee_inr"] == 0:
        fee_en, fee_hi = "There is no cancellation fee.", "Koi cancellation fee nahi hai."
    else:
        fee_en = f"The cancellation fee is {r['cancellation_fee_inr_spoken_en']}."
        fee_hi = f"Cancellation fee {r['cancellation_fee_inr_spoken_hi']} hai."
    items = r["pickup_items"]
    taken_hi = "le liya jayega" if len(items) == 1 else "le liye jayenge"
    return _say(
        f"{fee_en} The {_join_en(items)} will be collected from your registered store address "
        f"on {r['pickup_date_spoken_en']}.",
        f"{fee_hi} {_join_hi(items).capitalize()} aapke registered store address se "
        f"{r['pickup_date_spoken_hi']} ko {taken_hi}.",
    )


# ---------------------------------------------------------------- apply_retention_action

def retention_action(r: dict) -> dict:
    action = r["action"]
    if action == "switch_to_zero_rental":
        en = (
            "You are now on the zero rental plan. "
            f"A one-time fee of {r['one_time_fee_inr_spoken_en']} applies, and from your next billing cycle "
            f"you will pay {r['new_monthly_fee_inr_spoken_en']} a month."
        )
        hi = (
            "Aapka plan ab zero rental plan hai. "
            f"Ek baar ki fee {r['one_time_fee_inr_spoken_hi']} lagegi, aur agle billing cycle se "
            f"aap har mahine {r['new_monthly_fee_inr_spoken_hi']} denge."
        )
    elif action == "remote_troubleshoot":
        n = r["ready_within_minutes"]
        en = (
            "We have sent a remote restart to your speaker, and it should announce that it is ready "
            f"within {r['ready_within_minutes_spoken_en']}."
        )
        hi = (
            "Humne aapke speaker ko remote restart bhej diya hai, aur "
            f"{spoken.number_hi(n)} minute ke andar woh ready hone ki announcement karega."
        )
    elif action == "free_replacement":
        n = r["eta_hours"]
        en = f"A free replacement speaker has been booked and will reach you within {r['eta_hours_spoken_en']}."
        hi = (
            "Aapke liye muft replacement speaker book ho gaya hai, "
            f"jo {spoken.number_hi(n)} ghante ke andar aap tak pahunch jayega."
        )
    else:  # change_language
        n, lang = r["sync_within_hours"], r.get("new_language")
        within_hi = f"{spoken.number_hi(n)} ghante ke andar, agle sync par,"
        if lang:
            en = f"Your speaker's alert language will change to {lang} within {r['sync_within_hours_spoken_en']}, at its next sync."
            hi = f"Aapke speaker ki alert language {within_hi} {lang} ho jayegi."
        else:
            en = f"Your speaker's alert language will be updated within {r['sync_within_hours_spoken_en']}, at its next sync."
            hi = f"Aapke speaker ki alert language {within_hi} badal di jayegi."

    en += f" Your request reference is {spoken.digits_en(r['request_id'])}."
    hi += f" Aapka request reference number {spoken.digits_hi(r['request_id'])} hai."
    return _say(en, hi)


# ---------------------------------------------------------------- check_retention_options

def _offer(o: dict) -> dict:
    action = o["action"]
    if action == "switch_to_zero_rental":
        return _say(
            f"On the zero rental plan you pay a one-time fee of {o['one_time_fee_inr_spoken_en']} "
            f"and then {o['new_monthly_fee_inr_spoken_en']} a month, saving {o['monthly_saving_inr_spoken_en']} "
            f"every month, so it pays for itself in {o['break_even_months_spoken_en']}.",
            f"Zero rental plan mein ek baar {o['one_time_fee_inr_spoken_hi']} ki fee lagti hai, phir har mahine "
            f"sirf {o['new_monthly_fee_inr_spoken_hi']}, yaani har mahine {o['monthly_saving_inr_spoken_hi']} "
            f"ki bachat, aur {spoken.number_hi(o['break_even_months'])} mahine mein fee ki bharpai ho jaati hai.",
        )
    if action == "remote_troubleshoot":
        return _say(
            "We can restart your speaker remotely right now, which fixes most problems.",
            "Hum abhi aapka speaker remotely restart kar sakte hain, jisse zyaadatar problems theek ho jaati hain.",
        )
    if action == "free_replacement":
        return _say(
            f"If that does not fix it, we will send you a free replacement speaker within {o['eta_hours_spoken_en']}.",
            f"Agar isse theek nahi hota, to hum {spoken.number_hi(o['eta_hours'])} ghante ke andar "
            "muft replacement speaker bhej denge.",
        )
    if action == "change_language":
        lang = o["current_language"]
        return _say(
            f"We can change your speaker's alert language from {lang} to the language you prefer.",
            f"Hum aapke speaker ki alert language {lang} se badal kar aapki pasand ki bhasha kar sakte hain.",
        )
    return {}


def retention_options(r: dict) -> dict:
    return {**r, "offers": [{**o, **_offer(o)} for o in r["offers"]]}


# ---------------------------------------------------------------- run_device_diagnostics

def diagnostics(r: dict) -> dict:
    if r["healthy"]:
        signal_en = r["signal"]
        signal_hi = _SIGNAL_HI.get(r["signal"], r["signal"])
        return _say(
            f"Your speaker is working normally, with {r['battery_percent_spoken_en']} battery "
            f"and a {signal_en} network signal.",
            f"Aapka speaker theek se kaam kar raha hai, battery {r['battery_percent_spoken_hi']} hai "
            f"aur network signal {signal_hi} hai.",
        )

    causes_en, causes_hi = [], []  # (Hindi possessive, rest) so gender agrees: "ki battery", "ka signal"
    if ISSUE_LOW_BATTERY in r["issues"]:
        causes_en.append("battery is almost empty")
        causes_hi.append(("ki", "battery lagbhag khatam hai"))
    if ISSUE_WEAK_SIGNAL in r["issues"]:
        causes_en.append("network signal is weak")
        causes_hi.append(("ka", "network signal kamzor hai"))
    status = r["device_status"]

    if causes_en:
        en = "Your speaker's " + " and the ".join(causes_en)
        hi = f"Aapke speaker {causes_hi[0][0]} {causes_hi[0][1]}" + "".join(f" aur {rest}" for _, rest in causes_hi[1:])
        if status == "offline":
            en += ", so it has gone offline"
            hi += ", isliye woh offline ho gaya hai"
        elif status != "healthy":
            en += f", and it is reporting a {status} status"
            hi += f", aur woh {status} status dikha raha hai"
        return _say(en + ".", hi + ".")
    if status == "offline":
        return _say("Your speaker has gone offline.", "Aapka speaker offline ho gaya hai.")
    return _say(f"Your speaker is reporting a {status} status.", f"Aapka speaker {status} status dikha raha hai.")


# ---------------------------------------------------------------- schedule_callback

def callback(r: dict) -> dict:
    if r["escalation"]:
        who_en, who_hi, verb_hi = "A senior specialist", "Hamare senior specialist", "karenge"
    else:
        who_en, who_hi, verb_hi = "Our team", "Hamari team", "karegi"

    if r.get("callback_date"):
        d = date.fromisoformat(r["callback_date"])
        when_en = f"on {spoken.weekday_en(d)}, {r['callback_date_spoken_en']}"
        when_hi = f"{spoken.weekday_hi(d)}, {r['callback_date_spoken_hi']} ko"
        if r.get("callback_clock"):
            when_en += f", at {r['callback_clock_spoken_en']}"
            when_hi += f" {r['callback_clock_spoken_hi']}"
        en = f"{who_en} will call you {when_en}"
        en += "" if en.endswith(".") else "."  # "a.m." already ends the sentence
        hi = f"{who_hi} aapko {when_hi} call {verb_hi}."
    else:
        en = f"{who_en} will call you back at the time you asked for: {r['callback_time']}."
        hi = f"{who_hi} aapko aapke bataye gaye samay par call {verb_hi}: {r['callback_time']}."

    en += f" Your callback ticket number is {spoken.digits_en(r['ticket_id'])}."
    hi += f" Aapka callback ticket number {spoken.digits_hi(r['ticket_id'])} hai."
    return _say(en, hi)


# ---------------------------------------------------------------- dispatch

_SAYERS: dict[str, Callable[[dict], dict]] = {
    "process_cancellation": cancellation,
    "apply_retention_action": retention_action,
    "check_retention_options": retention_options,
    "run_device_diagnostics": diagnostics,
    "schedule_callback": callback,
}


def add_say(tool_name: str, result: dict) -> dict:
    """Return result with say_en / say_hi added (on each offer for check_retention_options)."""
    fn = _SAYERS.get(tool_name)
    if fn is None:
        return result
    if fn is retention_options:
        return fn(result)
    return {**result, **fn(result)}
