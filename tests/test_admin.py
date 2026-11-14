import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tools
from main import app

client = TestClient(app)
TOKEN = "test-token-123"
MERCHANTS_FILE = Path(tools.DATA_DIR) / "merchants.json"


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    return TOKEN


def reset(token=TOKEN):
    return client.post("/admin/reset", headers={"X-Admin-Token": token} if token else {})


def make_activity():
    tools.call_tool("process_cancellation", {"merchant_id": "M1001", "confirm": True})
    tools.call_tool("apply_retention_action", {"merchant_id": "M1002", "action": "free_replacement"})
    tools.call_tool("schedule_callback", {"merchant_id": "M1001", "time": "tomorrow 11 AM"})
    tools.call_tool("schedule_callback", {"merchant_id": "M1002", "time": "tomorrow 12 PM"})


def test_tools_never_change_merchant_data():
    file_before = MERCHANTS_FILE.read_text(encoding="utf-8")
    memory_before = json.dumps(tools.MERCHANTS, sort_keys=True)
    make_activity()
    tools.call_tool("apply_retention_action", {"merchant_id": "M1001", "action": "switch_to_zero_rental"})
    for mid in ("M1001", "M1002", "M1003"):
        tools.call_tool("process_cancellation", {"merchant_id": mid, "confirm": True})
    assert MERCHANTS_FILE.read_text(encoding="utf-8") == file_before
    assert json.dumps(tools.MERCHANTS, sort_keys=True) == memory_before
    assert tools.MERCHANTS["M1001"]["plan"] == "monthly"


def test_reset_clears_runtime_stores(admin_token, temp_tickets, temp_cancellations, temp_retention_actions):
    make_activity()
    assert temp_tickets.exists() and temp_cancellations.exists() and temp_retention_actions.exists()

    resp = reset()
    assert resp.status_code == 200
    assert resp.json() == {"status": "reset", "cleared": {"tickets": 2, "cancellations": 1, "retention_actions": 1}}
    assert not temp_tickets.exists() and not temp_cancellations.exists() and not temp_retention_actions.exists()


def test_after_reset_ids_and_cancellations_start_fresh(admin_token):
    make_activity()
    reset()
    ticket = tools.call_tool("schedule_callback", {"merchant_id": "M1003", "time": "tomorrow 11 AM"})
    cancel = tools.call_tool("process_cancellation", {"merchant_id": "M1002", "confirm": True})
    action = tools.call_tool("apply_retention_action", {"merchant_id": "M1001", "action": "remote_troubleshoot"})
    assert (ticket["ticket_id"], cancel["cancellation_id"], action["request_id"]) == ("CB-1001", "CN-1001", "RA-1001")


def test_reset_when_nothing_to_clear(admin_token):
    resp = reset()
    assert resp.status_code == 200
    assert resp.json()["cleared"] == {"tickets": 0, "cancellations": 0, "retention_actions": 0}


def test_reset_removes_corrupt_file(admin_token, temp_tickets):
    temp_tickets.write_text("{broken", encoding="utf-8")
    resp = reset()
    assert resp.json()["cleared"]["tickets"] is None
    assert not temp_tickets.exists()


@pytest.mark.parametrize("token", [None, "", "wrong-token"])
def test_reset_rejects_bad_token(admin_token, temp_tickets, token):
    make_activity()
    resp = reset(token)
    assert resp.status_code == 401
    assert temp_tickets.exists()


def test_reset_disabled_without_admin_token(monkeypatch, temp_tickets):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    make_activity()
    resp = reset("anything")
    assert resp.status_code == 503
    assert temp_tickets.exists()


def test_reset_is_post_only(admin_token):
    assert client.get("/admin/reset", headers={"X-Admin-Token": TOKEN}).status_code == 405
