import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

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
    out = vapi_call("get_merchant_profile", json.dumps({"phone": "9000000001"}))
    assert out["merchant_id"] == "M1001"


def test_legacy_tool_with_tool_call_list():
    out = vapi_call("run_device_diagnostics", {"merchant_id": "M1001"}, legacy=True)
    assert out["healthy"] is True


def test_multiple_calls_keep_ids_and_order():
    message = {"toolCallList": [
        {"id": "a", "function": {"name": "get_merchant_profile", "arguments": {"phone": "9000000002"}}},
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
            vapi_call("get_merchant_profile", {"phone": "9000000001"})
    finally:
        tools.logger.propagate = False
    assert any("Raw request body" in r.message and "9000000001" in r.message for r in caplog.records)


# ---------------------------------------------------------------- get_merchant_profile

@pytest.mark.parametrize("phone", ["9000000001", "+91 90000 00001", "+919000000001", "09000000001", "919000000001"])
def test_phone_normalisation(phone):
    assert vapi_call("get_merchant_profile", {"phone": phone})["name"] == "Ramesh Kirana"


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
    (offer,) = out["offers"]
    assert offer == {
        "action": "switch_to_zero_rental",
        "one_time_fee_inr": 999,
        "new_monthly_fee_inr": 25,
        "monthly_saving_inr": 100,
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


def test_schedule_callback_requires_time(temp_tickets):
    assert vapi_call("schedule_callback", {"merchant_id": "M1001"}) == {"error": "Missing time."}
    assert not temp_tickets.exists()


def test_corrupt_ticket_file_is_not_overwritten(temp_tickets):
    temp_tickets.write_text("{broken", encoding="utf-8")
    out = vapi_call("schedule_callback", {"merchant_id": "M1001", "time": "5 PM"})
    assert "error" in out
    assert temp_tickets.read_text(encoding="utf-8") == "{broken"
