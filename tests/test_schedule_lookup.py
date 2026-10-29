from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.tools import schedule_tool
from app.tools import bus_route_tool


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.fake_cursor = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.fake_cursor


def install_trips(monkeypatch, rows):
    @contextmanager
    def connection():
        yield FakeConnection(rows)

    monkeypatch.setattr(schedule_tool, "get_connection", connection)


def test_finds_time_at_matching_boarding_stop(monkeypatch):
    install_trips(monkeypatch, [(1, "Coastal", [
        {"stop": "Malappuram", "time": "08:00"},
        {"stop": "Kozhikode", "time": "09:30"},
    ])])

    result = schedule_tool.lookup_schedule(5, "Malappuram", "07:30", True)

    assert result["departure_time"] == "08:00"
    assert result["bus_name"] == "Coastal"


def test_user_requested_time_selects_next_available(monkeypatch):
    install_trips(monkeypatch, [(1, "Early", [
        {"stop": "A", "time": "08:00"},
    ]), (2, "Later", [{"stop": "A", "time": "10:00"}])])

    result = schedule_tool.lookup_schedule(2, "A", "09:00", True)

    assert result["departure_time"] == "10:00"
    assert result["bus_name"] == "Later"


def test_uses_current_india_local_time_when_not_explicit(monkeypatch):
    install_trips(monkeypatch, [(1, "Morning", [{"stop": "A", "time": "08:00"}]),
                                (2, "Evening", [{"stop": "A", "time": "18:00"}])])
    now = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    result = schedule_tool.lookup_schedule(2, "A", now=now)

    assert result["departure_time"] == "18:00"


def test_returns_only_one_best_time_across_multiple_trips(monkeypatch):
    install_trips(monkeypatch, [(3, "Later ID", [{"stop": "A", "time": "09:00"}]),
                                (2, "Earlier ID", [{"stop": "A", "time": "09:00"}]),
                                (1, "Too Early", [{"stop": "A", "time": "08:00"}])])

    result = schedule_tool.lookup_schedule(2, "A", "09:00", True)

    assert result["departure_time"] == "09:00"
    assert result["bus_name"] == "Earlier ID"
    assert result["status"] == "available"


def test_selects_earliest_next_day_when_all_times_passed(monkeypatch):
    install_trips(monkeypatch, [(1, "Late", [{"stop": "A", "time": "17:00"}]),
                                (2, "Early", [{"stop": "A", "time": "06:00"}])])

    result = schedule_tool.lookup_schedule(2, "A", "20:00", True)

    assert result["departure_time"] == "06:00"
    assert result["next_day"] is True


def test_missing_records_or_boarding_time_are_unavailable(monkeypatch):
    install_trips(monkeypatch, [(1, "No stop", [{"stop": "B", "time": "08:00"}]),
                                (2, "No time", [{"stop": "A", "time": None}])])

    result = schedule_tool.lookup_schedule(2, "A", "07:00", True)

    assert result["status"] == "unavailable"


def test_invalid_json_and_time_values_are_unavailable(monkeypatch):
    install_trips(monkeypatch, [(1, "Bad JSON", "not json"),
                                (2, "Bad time", [{"stop": "A", "time": "25:90"}])])

    result = schedule_tool.lookup_schedule(2, "A", "07:00", True)

    assert result["status"] == "unavailable"


def test_database_error_is_unavailable(monkeypatch):
    @contextmanager
    def broken_connection():
        raise RuntimeError("database is unavailable")
        yield

    monkeypatch.setattr(schedule_tool, "get_connection", broken_connection)

    result = schedule_tool.lookup_schedule(2, "A", "07:00", True)

    assert result["status"] == "unavailable"


def test_invalid_explicit_time_is_not_replaced_with_current_time(monkeypatch):
    result = schedule_tool.lookup_schedule(2, "A", "25:00", True)

    assert result["status"] == "unavailable"


def test_route_finder_attaches_time_for_first_leg_only(monkeypatch):
    route_result = {
        "status": "connected",
        "routes": [{
            "routes": [
                {"route_id": 10, "from": "A", "to": "B"},
                {"route_id": 20, "from": "B", "to": "C"},
            ],
            "stops": ["A", "B", "C"],
        }],
    }
    queried_legs = []
    monkeypatch.setattr(bus_route_tool, "find_routes", lambda *args: route_result)

    def lookup(**kwargs):
        queried_legs.append(kwargs)
        return {"status": "available", "departure_time": "08:00"}

    monkeypatch.setattr(bus_route_tool, "lookup_schedule", lookup)

    result = bus_route_tool.bus_route_finder("A", "C", "07:30", True)

    assert result["routes"][0]["schedule"]["departure_time"] == "08:00"
    assert len(queried_legs) == 1
    assert queried_legs[0]["route_id"] == 10
    assert queried_legs[0]["boarding_stop"] == "A"


def test_schedule_failure_does_not_fail_route_result(monkeypatch):
    route_result = {
        "status": "direct",
        "message": "Route options found.",
        "routes": [{"routes": [{"route_id": 10, "from": "A", "to": "B"}]}],
    }
    monkeypatch.setattr(bus_route_tool, "find_routes", lambda *args: route_result)

    def fail_lookup(**kwargs):
        raise RuntimeError("database is unavailable")

    monkeypatch.setattr(bus_route_tool, "lookup_schedule", fail_lookup)

    result = bus_route_tool.bus_route_finder("A", "B")

    assert result["status"] == "direct"
    assert result["routes"][0]["schedule"]["status"] == "unavailable"


def test_no_route_response_is_unchanged_and_skips_schedule(monkeypatch):
    route_result = {
        "status": "not_found",
        "message": "No valid forward bus connection was found.",
        "routes": [],
    }
    monkeypatch.setattr(bus_route_tool, "find_routes", lambda *args: route_result)

    def unexpected_lookup(**kwargs):
        pytest.fail("schedule lookup should not run when no route exists")

    monkeypatch.setattr(bus_route_tool, "lookup_schedule", unexpected_lookup)

    assert bus_route_tool.bus_route_finder("A", "Z") == route_result