import pytest

import tools


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


@pytest.fixture(autouse=True)
def temp_retention_actions(tmp_path, monkeypatch):
    path = tmp_path / "retention_actions.json"
    monkeypatch.setattr(tools, "RETENTION_ACTIONS_PATH", path)
    return path
