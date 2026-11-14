import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import spoken
import tools
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_tickets(tmp_path, monkeypatch):
    path = tmp_path / "tickets.json"
    monkeypatch.setattr(tools, "TICKETS_PATH", path)
    return path


@pytest.fixture(autouse=True)
def temp_cancellations(tmp_path, monkeypatch):
    path = tmp_path / "cancellations.json"
    monkeypatch.setattr(tools, "CANCELLATIONS_PATH", path)
    return path


def vapi_call(name, arguments, call_id="call_1", legacy=False):
    """POST a Vapi-shaped tool-call webhook and return the decoded result."""
    call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
    if legacy:
        message = {"type": "tool-calls", "toolWithToolCallList": [{"name": name, "toolCall": call}]}
    else:
        message = {"type": "tool-calls", "toolCallList": [call]}
    resp = client.post("/vapi/tools", json={"message": message})
    assert resp.status_code == 200
    (result,) = resp.json()["results"]
    assert result["toolCallId"] == call_id
    assert isinstance(result["result"], str)
    return json.loads(result["result"])


# ---------------------------------------------------------------- webhook plumbing

def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_arguments_as_json_string():
    out = vapi_call("get_merchant_profile", json.dumps({"phone": "9876543210"}))
    assert out["merchant_id"] == "M1001"


def test_legacy_tool_with_tool_call_list():
    out = vapi_call("run_device_diagnostics", {"merchant_id": "M1001"}, legacy=True)
    assert out["healthy"] is True


def test_multiple_calls_keep_ids_and_order():
    message = {"toolCallList": [
        {"id": "a", "function": {"name": "get_merchant_profile", "arguments": {"phone": "9123456780"}}},
        {"id": "b", "function": {"name": "run_device_diagnostics", "arguments": {"merchant_id": "M1002"}}},
    ]}
    results = client.post("/vapi/tools", json={"message": message}).json()["results"]
    assert [r["toolCallId"] for r in results] == ["a", "b"]


def test_unknown_tool_and_bad_arguments_return_errors():
    assert "error" in vapi_call("delete_everything", {})
    assert "error" in vapi_call("get_merchant_profile", "{not json")
    assert vapi_call("run_device_diagnostics", {}) == {"error": "Missing merchant_id."}


def test_invalid_body_is_400():
    assert client.post("/vapi/tools", content=b"nope").status_code == 400
    assert client.post("/vapi/tools", json={"foo": 1}).status_code == 400


def test_raw_body_is_logged(caplog):
    tools.logger.propagate = True  # let caplog see our dedicated logger
    try:
        with caplog.at_level("INFO", logger="vapi_tools"):
            vapi_call("get_merchant_profile", {"phone": "9876543210"})
    finally:
        tools.logger.propagate = False
    assert any("Raw request body" in r.message and "9876543210" in r.message for r in caplog.records)


# ---------------------------------------------------------------- get_merchant_profile

@pytest.mark.parametrize("phone", ["9876543210", "+91 98765 43210", "+919876543210", "09876543210", "919876543210"])
def test_phone_normalisation(phone):
    assert vapi_call("get_merchant_profile", {"phone": phone})["name"] == "Ramesh Kirana"


@pytest.mark.parametrize("phone, merchant_id", [
    # M1002's own number starts with 91; it must not be mistaken for the country code.
    ("9123456780", "M1002"), ("+91 91234 56780", "M1002"), ("919123456780", "M1002"), ("09123456780", "M1002"),
    ("9988776655", "M1003"), ("+91-99887-76655", "M1003"),
])
def test_each_merchant_found_by_phone(phone, merchant_id):
    assert vapi_call("get_merchant_profile", {"phone": phone})["merchant_id"] == merchant_id


def test_old_mock_numbers_no_longer_match():
    for old in ("9000000001", "9000000002", "9000000003"):
        assert "error" in vapi_call("get_merchant_profile", {"phone": old})


def test_profile_fields():
    out = vapi_call("get_merchant_profile", {"phone": "9876543210"})
    assert out == {
        "merchant_id": "M1001",
        "merchant_id_spoken": "M, one zero zero one",
        "name": "Ramesh Kirana",
        "plan": "monthly",
        "plan_name_spoken": "monthly plan",
        "monthly_fee_inr": 125,
        "monthly_fee_inr_spoken_en": "one hundred twenty-five rupees",
        "monthly_fee_inr_spoken_hi": "ek sau pachchees rupaye",
        "tenure_months": 9,
        "payments_last_month": 410,
        "speaker_alert_language": "Hindi",
    }
    assert "language" not in out


def test_unknown_phone():
    assert "error" in vapi_call("get_merchant_profile", {"phone": "9999999999"})


# ---------------------------------------------------------------- run_device_diagnostics

def test_diagnostics_healthy():
    out = vapi_call("run_device_diagnostics", {"merchant_id": "M1001"})
    assert out["healthy"] is True and out["issues"] == [] and "suggested_fix" not in out


def test_diagnostics_offline_device():
    out = vapi_call("run_device_diagnostics", {"merchant_id": "m1002"})
    assert out["healthy"] is False
    assert out["issues"] == ["device is offline", "battery critically low", "weak signal"]
    assert out["last_alert"] == "6 days ago"
    assert "charge" in out["suggested_fix"].lower()


def test_unknown_merchant():
    assert "error" in vapi_call("run_device_diagnostics", {"merchant_id": "M9999"})


# ---------------------------------------------------------------- check_retention_options

def test_cost_offers_zero_rental_with_savings():
    out = vapi_call("check_retention_options", {"merchant_id": "M1001", "reason_code": "COST"})
    assert out["cost_per_payment_paise"] == 30  # 12500 / 410 = 30.49
    assert out["cost_per_payment_paise_spoken_en"] == "about thirty paise per payment"
    assert out["cost_per_payment_paise_spoken_hi"] == "har payment par lagbhag tees paise"
    (offer,) = out["offers"]
    assert offer == {
        "action": "switch_to_zero_rental",
        "one_time_fee_inr": 999,
        "one_time_fee_inr_spoken_en": "nine hundred ninety-nine rupees",
        "one_time_fee_inr_spoken_hi": "nau sau ninyanve rupaye",
        "new_monthly_fee_inr": 25,
        "new_monthly_fee_inr_spoken_en": "twenty-five rupees",
        "new_monthly_fee_inr_spoken_hi": "pachchees rupaye",
        "monthly_saving_inr": 100,
        "monthly_saving_inr_spoken_en": "one hundred rupees",
        "monthly_saving_inr_spoken_hi": "ek sau rupaye",
        "break_even_months": 10,
    }


@pytest.mark.parametrize("reason", ["NOT_USEFUL", "SWITCHING_COMPETITOR", "switching competitor"])
def test_reasons_aliased_to_cost(reason):
    out = vapi_call("check_retention_options", {"merchant_id": "M1001", "reason_code": reason})
    assert out["offers"][0]["action"] == "switch_to_zero_rental"
    assert out["cost_per_payment_paise"] == 30


def test_cost_on_zero_rental_plan_has_no_offer():
    out = vapi_call("check_retention_options", {"merchant_id": "M1003", "reason_code": "COST"})
    assert out["offers"] == []
    assert out["cost_per_payment_paise"] == 17  # 2500 / 150 = 16.67
    assert "note" in out


def test_not_working_offers_in_order():
    out = vapi_call("check_retention_options", {"merchant_id": "M1002", "reason_code": "NOT_WORKING"})
    assert [o["action"] for o in out["offers"]] == ["remote_troubleshoot", "free_replacement"]
    assert out["offers"][1]["eta_hours"] == 48
    assert out["offers"][1]["reason"] == "device fault"


def test_language_or_volume():
    out = vapi_call("check_retention_options", {"merchant_id": "M1001", "reason_code": "LANGUAGE_OR_VOLUME"})
    assert out["offers"] == [{"action": "change_language", "current_language": "Hindi"}]


def test_closing_or_moving_releases():
    out = vapi_call("check_retention_options", {"merchant_id": "M1001", "reason_code": "CLOSING_OR_MOVING"})
    assert out["offers"] == [] and out["recommendation"] == "release"


def test_unknown_reason_code():
    assert "error" in vapi_call("check_retention_options", {"merchant_id": "M1001", "reason_code": "BORED"})


# ---------------------------------------------------------------- apply_retention_action

@pytest.mark.parametrize("action", ["switch_to_zero_rental", "remote_troubleshoot", "free_replacement", "change_language"])
def test_apply_action(action):
    out = vapi_call("apply_retention_action", {"merchant_id": "M1002", "action": action})
    assert out["status"] == "applied" and out["action"] == action and out["message"]


def test_apply_zero_rental_when_already_on_it():
    out = vapi_call("apply_retention_action", {"merchant_id": "M1003", "action": "switch_to_zero_rental"})
    assert "already" in out["error"]


def test_apply_unknown_action():
    assert "error" in vapi_call("apply_retention_action", {"merchant_id": "M1001", "action": "free_money"})


# ---------------------------------------------------------------- fee logic + process_cancellation

@pytest.mark.parametrize("tenure, before, fee", [
    (0, 0, 1), (5, 0, 1), (5, 1, 550), (5, 3, 550),
    (6, 0, 1), (12, 0, 1), (6, 1, 400), (12, 2, 400),
    (13, 0, 0), (13, 1, 0), (40, 5, 0),
])
def test_cancellation_fee(tenure, before, fee):
    assert tools.cancellation_fee(tenure, before) == fee


@pytest.mark.parametrize("merchant_id, fee", [("M1001", 1), ("M1002", 1), ("M1003", 0)])
def test_cancellation_quote_does_not_cancel(merchant_id, fee, temp_cancellations):
    out = vapi_call("process_cancellation", {"merchant_id": merchant_id, "reason_code": "COST", "confirm": False})
    assert out["status"] == "quote"
    assert out["cancellation_fee_inr"] == fee
    assert out["pickup_date"] == (tools.today_ist() + timedelta(days=3)).isoformat()
    assert out["pickup_items"] == ["speaker", "charging adapter"]
    assert "cancellation_id" not in out
    assert not temp_cancellations.exists()


@pytest.mark.parametrize("merchant_id, fee", [("M1001", 1), ("M1002", 1), ("M1003", 0)])
def test_cancellation_confirm_records_it(merchant_id, fee, temp_cancellations):
    out = vapi_call("process_cancellation", {"merchant_id": merchant_id, "reason_code": "COST", "confirm": True})
    assert out["status"] == "cancellation_confirmed"
    assert out["cancellation_id"] == "CN-1001"
    assert out["cancellation_fee_inr"] == fee
    assert out["pickup_items"] == ["speaker", "charging adapter"]
    (record,) = json.loads(temp_cancellations.read_text(encoding="utf-8"))
    assert record["merchant_id"] == merchant_id
    assert record["cancellation_fee_inr"] == fee
    assert record["reason_code"] == "COST"


def test_quote_and_confirm_match():
    args = {"merchant_id": "M1002", "reason_code": "NOT_WORKING"}
    quote = vapi_call("process_cancellation", {**args, "confirm": False})
    done = vapi_call("process_cancellation", {**args, "confirm": True})
    for key in ("cancellation_fee_inr", "pickup_date", "pickup_items"):
        assert quote[key] == done[key]


def test_cancellation_requires_confirm(temp_cancellations):
    out = vapi_call("process_cancellation", {"merchant_id": "M1001", "reason_code": "COST"})
    assert out == {"error": "Missing confirm."}
    assert not temp_cancellations.exists()


@pytest.mark.parametrize("raw, status", [("true", "cancellation_confirmed"), ("false", "quote"), ("no", "quote")])
def test_confirm_coerced_from_strings(raw, status):
    out = vapi_call("process_cancellation", {"merchant_id": "M1001", "confirm": raw})
    assert out["status"] == status


def test_repeated_confirm_does_not_duplicate(temp_cancellations):
    first = vapi_call("process_cancellation", {"merchant_id": "M1001", "confirm": True})
    second = vapi_call("process_cancellation", {"merchant_id": "M1001", "confirm": True})
    other = vapi_call("process_cancellation", {"merchant_id": "M1002", "confirm": True})
    assert first == second
    assert other["cancellation_id"] == "CN-1002"
    assert len(json.loads(temp_cancellations.read_text(encoding="utf-8"))) == 2


# ---------------------------------------------------------------- schedule_callback

def test_schedule_callback_saves_ticket(temp_tickets):
    out = vapi_call("schedule_callback", {
        "merchant_id": "M1002",
        "time": "tomorrow 11 AM",
        "reason": "NOT_WORKING",
        "escalation": True,
        "summary": "Speaker offline for 6 days, troubleshooting failed.",
    })
    assert out["status"] == "scheduled"
    assert out["ticket_id"] == "CB-1001"
    assert out["escalation"] is True

    (ticket,) = json.loads(temp_tickets.read_text(encoding="utf-8"))
    assert ticket["ticket_id"] == "CB-1001"
    assert ticket["merchant_id"] == "M1002"
    assert ticket["callback_time"] == "tomorrow 11 AM"
    assert ticket["reason"] == "NOT_WORKING"
    assert ticket["escalation"] is True
    assert ticket["summary"].startswith("Speaker offline")
    assert ticket["status"] == "open"


def test_ticket_ids_increment_from_existing(temp_tickets):
    temp_tickets.write_text(json.dumps([{"ticket_id": "CB-1041"}]), encoding="utf-8")
    first = vapi_call("schedule_callback", {"merchant_id": "M1001", "time": "5 PM"})
    second = vapi_call("schedule_callback", {"merchant_id": "M1003", "time": "6 PM"})
    assert (first["ticket_id"], second["ticket_id"]) == ("CB-1042", "CB-1043")
    assert len(json.loads(temp_tickets.read_text(encoding="utf-8"))) == 3


@pytest.mark.parametrize("raw, expected", [("true", True), ("false", False), ("no", False), (None, False)])
def test_escalation_coerced_from_strings(raw, expected):
    out = vapi_call("schedule_callback", {"merchant_id": "M1001", "time": "5 PM", "escalation": raw})
    assert out["escalation"] is expected


def test_escalation_defaults_false_and_optional_fields(temp_tickets):
    out = vapi_call("schedule_callback", {"merchant_id": "M1001", "time": "5 PM"})
    assert out["escalation"] is False
    (ticket,) = json.loads(temp_tickets.read_text(encoding="utf-8"))
    assert ticket["reason"] is None and ticket["summary"] is None


@pytest.mark.parametrize("merchant_id", ["UNKNOWN", "unknown", " Unknown "])
def test_schedule_callback_for_unknown_merchant(merchant_id, temp_tickets):
    out = vapi_call("schedule_callback", {
        "merchant_id": merchant_id,
        "time": "today 4 PM",
        "reason": "NOT_WORKING",
        "escalation": True,
        "summary": "Caller could not be identified by phone.",
    })
    assert out["status"] == "scheduled" and out["ticket_id"] == "CB-1001"
    (ticket,) = json.loads(temp_tickets.read_text(encoding="utf-8"))
    assert ticket["merchant_id"] == "UNKNOWN"
    assert ticket["merchant_name"] is None and ticket["phone"] is None
    assert ticket["summary"] == "Caller could not be identified by phone."


def test_unknown_is_only_special_for_schedule_callback(temp_tickets):
    assert "error" in vapi_call("schedule_callback", {"merchant_id": "M9999", "time": "4 PM"})
    assert "error" in vapi_call("run_device_diagnostics", {"merchant_id": "UNKNOWN"})
    assert "error" in vapi_call("process_cancellation", {"merchant_id": "UNKNOWN", "confirm": True})
    assert not temp_tickets.exists()


def test_schedule_callback_requires_time(temp_tickets):
    assert vapi_call("schedule_callback", {"merchant_id": "M1001"}) == {"error": "Missing time."}
    assert not temp_tickets.exists()


def test_corrupt_ticket_file_is_not_overwritten(temp_tickets):
    temp_tickets.write_text("{broken", encoding="utf-8")
    out = vapi_call("schedule_callback", {"merchant_id": "M1001", "time": "5 PM"})
    assert "error" in out
    assert temp_tickets.read_text(encoding="utf-8") == "{broken"


# ---------------------------------------------------------------- spoken fields in tool results

def test_diagnostics_battery_spoken():
    out = vapi_call("run_device_diagnostics", {"merchant_id": "M1002"})
    assert out["battery_percent_spoken_en"] == "four percent"
    assert out["battery_percent_spoken_hi"] == "chaar percent"
    assert out["merchant_id_spoken"] == "M, one zero zero two"


def test_zero_rental_plan_name_spoken():
    out = vapi_call("get_merchant_profile", {"phone": "9988776655"})
    assert out["plan_name_spoken"] == "zero rental plan"
    note = vapi_call("check_retention_options", {"merchant_id": "M1003", "reason_code": "COST"})["note"]
    assert "zero rental plan" in note and "zero_rental" not in note


def test_apply_zero_rental_has_spoken_money():
    out = vapi_call("apply_retention_action", {"merchant_id": "M1001", "action": "switch_to_zero_rental"})
    assert out["one_time_fee_inr_spoken_hi"] == "nau sau ninyanve rupaye"
    assert out["new_monthly_fee_inr_spoken_en"] == "twenty-five rupees"
    assert "999" not in out["message"] and "nine hundred ninety-nine rupees" in out["message"]


@pytest.mark.parametrize("confirm", [False, True])
def test_cancellation_spoken_fee_and_date(confirm):
    out = vapi_call("process_cancellation", {"merchant_id": "M1001", "confirm": confirm})
    pickup = tools.today_ist() + timedelta(days=3)
    assert out["cancellation_fee_inr_spoken_en"] == "one rupee"
    assert out["cancellation_fee_inr_spoken_hi"] == "ek rupaya"
    assert out["pickup_date_spoken_en"] == spoken.date_en(pickup)
    assert out["pickup_date_spoken_hi"] == spoken.date_hi(pickup)
    if confirm:
        assert out["cancellation_id_spoken"] == "C N, one zero zero one"


def test_cancellation_zero_fee_spoken():
    out = vapi_call("process_cancellation", {"merchant_id": "M1003", "confirm": False})
    assert out["cancellation_fee_inr_spoken_en"] == "zero rupees"
    assert out["cancellation_fee_inr_spoken_hi"] == "shunya rupaye"


def test_ticket_id_spoken(temp_tickets):
    temp_tickets.write_text(json.dumps([{"ticket_id": "CB-1041"}]), encoding="utf-8")
    out = vapi_call("schedule_callback", {"merchant_id": "M1001", "time": "5 PM"})
    assert out["ticket_id"] == "CB-1042"
    assert out["ticket_id_spoken"] == "C B, one zero four two"


def test_unknown_merchant_id_gets_no_spoken_reference():
    out = vapi_call("schedule_callback", {"merchant_id": "UNKNOWN", "time": "5 PM"})
    assert "merchant_id_spoken" not in out


def test_spoken_failure_keeps_result(monkeypatch):
    def boom(_):
        raise RuntimeError("bug")
    monkeypatch.setattr(spoken, "add_spoken", boom)
    out = vapi_call("get_merchant_profile", {"phone": "9876543210"})
    assert out["name"] == "Ramesh Kirana" and "plan_name_spoken" not in out
