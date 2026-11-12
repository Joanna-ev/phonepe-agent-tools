"""Tool implementations for the Vapi voice agent.

Every tool returns a small dict that main.py serialises into the speakable
`result` string. Caller-facing problems raise ToolError; its message is
returned to the agent as {"error": "..."} so it can be read out.
"""

from __future__ import annotations

import inspect
import json
import logging
import math
import os
import re
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("vapi_tools")

DATA_DIR = Path(__file__).resolve().parent / "data"
TICKETS_PATH = Path(os.environ.get("TICKETS_PATH", DATA_DIR / "tickets.json"))
CANCELLATIONS_PATH = Path(os.environ.get("CANCELLATIONS_PATH", DATA_DIR / "cancellations.json"))
TICKET_ID_START = 1001

# Pickup dates are quoted to Indian merchants; Render runs in UTC.
IST = timezone(timedelta(hours=5, minutes=30))

LOW_BATTERY_PERCENT = 15

_store_lock = threading.Lock()  # guards tickets.json and cancellations.json


class ToolError(Exception):
    """A problem the agent should say back to the caller."""


def _load_json(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


MERCHANTS: dict[str, dict] = {m["merchant_id"]: m for m in _load_json("merchants.json")}
RULES: dict = _load_json("rules.json")


# ---------------------------------------------------------------- helpers

def today_ist():
    return datetime.now(IST).date()


def normalise_phone(phone: Any) -> str:
    """'+91 90000 00001', '09000000001', '919000000001' -> '9000000001'."""
    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    return digits.lstrip("0")


def normalise_reason(reason_code: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(reason_code or "").strip()).upper()


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return bool(value)


def get_merchant(merchant_id: Any) -> dict:
    key = str(merchant_id or "").strip().upper()
    merchant = MERCHANTS.get(key)
    if merchant is None:
        raise ToolError(f"No merchant found with ID {merchant_id}.")
    return merchant


def cancellation_fee(tenure_months: int, requests_before: int) -> int:
    """Fee in rupees. Tiers in rules.json use inclusive max_tenure_months."""
    first_request = requests_before == 0
    for tier in RULES["cancellation"]["fee_tiers"]:
        if tier["max_tenure_months"] is None or tenure_months <= tier["max_tenure_months"]:
            return tier["first_request_inr"] if first_request else tier["repeat_request_inr"]
    raise RuntimeError("rules.json fee_tiers must end with an open-ended tier")


def cost_per_payment_paise(merchant: dict) -> int | None:
    payments = merchant["payments_last_month"]
    if not payments:
        return None
    return round(merchant["monthly_fee_inr"] * 100 / payments)


def _build_offer(name: str, merchant: dict) -> dict | None:
    config = RULES["offers"][name]
    if name == "switch_to_zero_rental":
        if merchant["plan"] not in config["eligible_plans"]:
            return None
        saving = merchant["monthly_fee_inr"] - config["new_monthly_fee_inr"]
        if saving <= 0:
            return None
        return {
            "action": name,
            "one_time_fee_inr": config["one_time_fee_inr"],
            "new_monthly_fee_inr": config["new_monthly_fee_inr"],
            "monthly_saving_inr": saving,
            "break_even_months": math.ceil(config["one_time_fee_inr"] / saving),
        }
    if name == "change_language":
        return {"action": name, "current_language": merchant["language"]}
    return {"action": name, **config}


# ---------------------------------------------------------------- tools

def get_merchant_profile(phone: str) -> dict:
    wanted = normalise_phone(phone)
    if not wanted:
        raise ToolError("I need the registered phone number to look up the account.")
    for m in MERCHANTS.values():
        if normalise_phone(m["phone"]) == wanted:
            return {
                "merchant_id": m["merchant_id"],
                "name": m["name"],
                "plan": m["plan"],
                "monthly_fee_inr": m["monthly_fee_inr"],
                "tenure_months": m["tenure_months"],
                "payments_last_month": m["payments_last_month"],
                "language": m["language"],
            }
    raise ToolError("No merchant found for that phone number.")


def run_device_diagnostics(merchant_id: str) -> dict:
    m = get_merchant(merchant_id)
    d = m["device"]
    issues, fixes = [], []
    if d["battery"] < LOW_BATTERY_PERCENT:
        issues.append("battery critically low")
        fixes.append("charge the speaker for 30 minutes")
    if d["signal"] == "weak":
        issues.append("weak signal")
        fixes.append("move it closer to a window or the shop entrance")
    if d["status"] != "healthy":
        issues.insert(0, f"device is {d['status']}")
        fixes.append("then hold the power button for 5 seconds to restart it")

    result = {
        "merchant_id": m["merchant_id"],
        "device_status": d["status"],
        "battery_percent": d["battery"],
        "signal": d["signal"],
        "last_alert": d["last_alert"],
        "healthy": not issues,
        "issues": issues,
    }
    if fixes:
        result["suggested_fix"] = ", ".join(fixes).capitalize() + "."
    return result


def check_retention_options(merchant_id: str, reason_code: str) -> dict:
    m = get_merchant(merchant_id)
    reason = normalise_reason(reason_code)
    rule = RULES["reason_codes"].get(reason)
    if rule is None:
        valid = ", ".join(RULES["reason_codes"])
        raise ToolError(f"Unknown reason code {reason_code}. Use one of: {valid}.")
    if "same_as" in rule:
        rule = RULES["reason_codes"][rule["same_as"]]

    offers = [o for o in (_build_offer(n, m) for n in rule["offers"]) if o]
    result: dict = {"merchant_id": m["merchant_id"], "reason_code": reason}
    if rule.get("include_cost_per_payment"):
        result["cost_per_payment_paise"] = cost_per_payment_paise(m)
    result["offers"] = offers
    if "recommendation" in rule:
        result["recommendation"] = rule["recommendation"]
    elif rule["offers"] and not offers:
        result["note"] = f"No offers apply; merchant is already on the {m['plan']} plan."
    return result


def apply_retention_action(merchant_id: str, action: str, language: str | None = None) -> dict:
    m = get_merchant(merchant_id)
    action = str(action or "").strip().lower()
    if action not in RULES["offers"]:
        valid = ", ".join(RULES["offers"])
        raise ToolError(f"Unknown action {action}. Use one of: {valid}.")

    if action == "switch_to_zero_rental":
        offer = _build_offer(action, m)
        if offer is None:
            raise ToolError(f"{m['name']} is already on the {m['plan']} plan.")
        message = (
            f"Switched to zero rental. One-time fee {offer['one_time_fee_inr']} rupees, "
            f"then {offer['new_monthly_fee_inr']} rupees a month from the next cycle."
        )
    elif action == "remote_troubleshoot":
        message = "Remote restart sent. The speaker should announce it is ready within 2 minutes."
    elif action == "free_replacement":
        eta = RULES["offers"][action]["eta_hours"]
        message = f"Free replacement booked. The new speaker will arrive within {eta} hours."
    else:  # change_language
        target = f" to {language}" if language else ""
        message = f"Speaker language will change{target} on its next sync, within 1 hour."

    logger.info("Retention action applied: %s for %s", action, m["merchant_id"])
    return {"status": "applied", "merchant_id": m["merchant_id"], "action": action, "message": message}


def process_cancellation(merchant_id: str, confirm: Any, reason_code: str | None = None) -> dict:
    """confirm=false returns a quote only; confirm=true records the cancellation.

    The agent must read the quote's fee and pickup details to the merchant and
    get their agreement before calling again with confirm=true.
    """
    m = get_merchant(merchant_id)
    cfg = RULES["cancellation"]
    fee = cancellation_fee(m["tenure_months"], m["cancellation_requests_before"])
    pickup = today_ist() + timedelta(days=cfg["pickup_days_from_today"])
    details = {
        "merchant_id": m["merchant_id"],
        "reason_code": normalise_reason(reason_code) or None,
        "cancellation_fee_inr": fee,
        "pickup_date": pickup.isoformat(),
        "pickup_day": f"{pickup:%A}, {pickup.day} {pickup:%B}",
        "pickup_items": cfg["pickup_items"],
    }

    if not _to_bool(confirm):
        return {
            "status": "quote",
            **details,
            "message": "Not cancelled yet. Tell the merchant the fee and pickup, then confirm.",
        }

    with _store_lock:
        records = _read_list(CANCELLATIONS_PATH)
        # Retries or a repeated confirm must not create a second cancellation.
        existing = next((r for r in records if r["merchant_id"] == m["merchant_id"]), None)
        if existing is None:
            existing = {
                "cancellation_id": _next_id(records, "cancellation_id", "CN"),
                **details,
                "merchant_name": m["name"],
                "created_at": datetime.now(IST).isoformat(timespec="seconds"),
            }
            records.append(existing)
            _write_list(CANCELLATIONS_PATH, records)
            logger.info("Cancellation recorded: %s for %s", existing["cancellation_id"], m["merchant_id"])

    return {
        "status": "cancellation_confirmed",
        "cancellation_id": existing["cancellation_id"],
        **{k: existing[k] for k in details},
    }


def _read_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)  # a corrupt file raises rather than being overwritten


def _write_list(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _next_id(items: list[dict], key: str, prefix: str) -> str:
    numbers = [
        int(match.group(1))
        for item in items
        if (match := re.fullmatch(rf"{prefix}-(\d+)", str(item.get(key, ""))))
    ]
    return f"{prefix}-{max(numbers, default=TICKET_ID_START - 1) + 1}"


def schedule_callback(
    merchant_id: str,
    time: str,
    reason: str | None = None,
    escalation: Any = False,
    summary: str | None = None,
) -> dict:
    m = get_merchant(merchant_id)
    if not str(time or "").strip():
        raise ToolError("Please tell me a time for the callback.")
    escalation = _to_bool(escalation)

    with _store_lock:
        tickets = _read_list(TICKETS_PATH)
        ticket = {
            "ticket_id": _next_id(tickets, "ticket_id", "CB"),
            "merchant_id": m["merchant_id"],
            "merchant_name": m["name"],
            "phone": m["phone"],
            "callback_time": str(time).strip(),
            "reason": reason,
            "escalation": escalation,
            "summary": summary,
            "status": "open",
            "created_at": datetime.now(IST).isoformat(timespec="seconds"),
        }
        tickets.append(ticket)
        _write_list(TICKETS_PATH, tickets)

    team = "a senior specialist" if escalation else "our team"
    return {
        "status": "scheduled",
        "ticket_id": ticket["ticket_id"],
        "callback_time": ticket["callback_time"],
        "escalation": escalation,
        "message": f"Callback booked with {team} for {ticket['callback_time']}.",
    }


# ---------------------------------------------------------------- dispatch

TOOLS = {
    fn.__name__: fn
    for fn in (
        get_merchant_profile,
        run_device_diagnostics,
        check_retention_options,
        apply_retention_action,
        process_cancellation,
        schedule_callback,
    )
}


def call_tool(name: str | None, args: dict) -> dict:
    """Run a tool by name. Never raises; failures come back as {"error": ...}."""
    fn = TOOLS.get(name or "")
    if fn is None:
        return {"error": f"Unknown tool {name}."}

    params = inspect.signature(fn).parameters
    kwargs = {k: v for k, v in args.items() if k in params}
    missing = [p for p, spec in params.items() if spec.default is spec.empty and kwargs.get(p) in (None, "")]
    if missing:
        return {"error": f"Missing {', '.join(missing)}."}

    try:
        return fn(**kwargs)
    except ToolError as e:
        return {"error": str(e)}
    except Exception:
        logger.exception("Tool %s failed with args %s", name, args)
        return {"error": "Something went wrong on our side. Please try again."}
