from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.db.postgres import get_connection


INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _parse_schedule_time(value: Any) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        return None
    return parsed


def lookup_schedule(
    route_id: int,
    boarding_stop: str,
    requested_time: str | None = None,
    requested_time_explicit: bool = False,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Find one next scheduled time at the boarding stop on a route."""
    from app.tools.bus_route_tool import (
        build_place_index,
        normalize_place,
        resolve_place,
    )

    unavailable = {
        "status": "unavailable",
        "message": "The schedule time could not be found in the database.",
    }

    if requested_time_explicit:
        reference_time = _parse_schedule_time(requested_time)
        if reference_time is None:
            return unavailable
    else:
        local_now = now or datetime.now(INDIA_TIMEZONE)
        if local_now.tzinfo is None:
            local_now = local_now.replace(tzinfo=INDIA_TIMEZONE)
        reference_time = local_now.astimezone(INDIA_TIMEZONE).time().replace(
            second=0, microsecond=0
        )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT trip_id, bus_name, stops_list "
                    "FROM trip WHERE route_id = %s ORDER BY trip_id",
                    (route_id,),
                )
                trips = cur.fetchall()
    except Exception:
        return unavailable

    candidates: list[tuple[int, int, str, time]] = []
    for trip_id, bus_name, stops_list in trips:
        if isinstance(stops_list, str):
            try:
                stops_list = json.loads(stops_list)
            except (TypeError, ValueError):
                continue
        if not isinstance(stops_list, list):
            continue

        named_stops = [
            str(item["stop"]).strip()
            for item in stops_list
            if isinstance(item, dict)
            and isinstance(item.get("stop"), str)
            and item["stop"].strip()
        ]
        boarding_match = resolve_place(
            boarding_stop, build_place_index([{"stops": named_stops}])
        )
        if not boarding_match["matched"]:
            continue
        matched_normalized = normalize_place(boarding_match["matched"])

        for item in stops_list:
            if not isinstance(item, dict):
                continue
            stop_name = item.get("stop")
            if not isinstance(stop_name, str) or normalize_place(stop_name) != matched_normalized:
                continue
            scheduled_time = _parse_schedule_time(item.get("time"))
            if scheduled_time is None:
                continue
            minute_of_day = scheduled_time.hour * 60 + scheduled_time.minute
            reference_minute = reference_time.hour * 60 + reference_time.minute
            candidates.append((minute_of_day, int(trip_id), str(bus_name), scheduled_time))
            break

    if not candidates:
        return unavailable

    reference_minute = reference_time.hour * 60 + reference_time.minute
    later_today = [candidate for candidate in candidates if candidate[0] >= reference_minute]
    next_day = not later_today
    selected = min(later_today or candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return {
        "status": "available",
        "bus_name": selected[2],
        "departure_time": selected[3].strftime("%H:%M"),
        "next_day": next_day,
        "message": (
            "This is the next scheduled occurrence tomorrow."
            if next_day
            else "Next scheduled boarding time."
        ),
    }