from __future__ import annotations

from collections import deque
from typing import Any

from rapidfuzz import fuzz, process

from app.config import settings
from app.db.postgres import get_connection
from app.tools.schedule_tool import lookup_schedule


def normalize_place(place: str) -> str:
    """Normalize a place name for comparison."""
    return " ".join(str(place).strip().casefold().split())


# Alternate names grouped together. The resolver chooses the spelling
# actually present in the database, rather than assuming one canonical form.
PLACE_ALIAS_GROUPS = (
    {"calicut", "kozhikode"},
    {"shanti", "shanthi"},
    {"nilampur", "nilambur"},
    {"pattikad", "pattikkad"},
)


def load_routes() -> list[dict[str, Any]]:
    """Load route rows from the user's exact PostgreSQL `route` table."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT route_id, route_name, stops FROM route ORDER BY route_id"
            )
            rows = cur.fetchall()

    routes: list[dict[str, Any]] = []
    for route_id, route_name, stops in rows:
        # psycopg normally decodes JSONB arrays into Python lists.
        if isinstance(stops, str):
            import json
            stops = json.loads(stops)
        if not isinstance(stops, list):
            continue
        clean_stops = [str(stop).strip() for stop in stops if str(stop).strip()]
        routes.append(
            {
                "route_id": route_id,
                "route_name": route_name,
                "stops": clean_stops,
                "normalized_stops": [normalize_place(s) for s in clean_stops],
            }
        )
    return routes


def build_place_index(routes: list[dict[str, Any]]) -> dict[str, str]:
    """Map normalized database stop names to their display spelling."""
    index: dict[str, str] = {}
    for route in routes:
        for stop in route["stops"]:
            normalized = normalize_place(stop)
            if normalized:
                index.setdefault(normalized, stop)
    return index


def resolve_place(user_place: str, place_index: dict[str, str]) -> dict[str, Any]:
    """Resolve exact names, known alternate spellings, then fuzzy spelling."""
    raw = str(user_place).strip()
    normalized = normalize_place(raw)

    if normalized in place_index:
        return {"input": raw, "matched": place_index[normalized], "normalized": normalized, "method": "exact", "score": 100}

    for group in PLACE_ALIAS_GROUPS:
        if normalized in group:
            for alias in group:
                if alias in place_index:
                    return {"input": raw, "matched": place_index[alias], "normalized": alias, "method": "alias", "score": 100}

    choices = list(place_index)
    match = process.extractOne(normalized, choices, scorer=fuzz.WRatio, score_cutoff=72) if choices else None
    if not match:
        return {"input": raw, "matched": None, "normalized": None, "method": "not_found", "score": 0}

    matched_normalized, score, _ = match
    return {"input": raw, "matched": place_index[matched_normalized], "normalized": matched_normalized, "method": "fuzzy", "score": round(float(score), 2)}


def _route_segment(route: dict[str, Any], start_index: int, end_index: int) -> dict[str, Any]:
    """Describe the part of one route travelled by the passenger."""
    return {
        "route_id": route["route_id"],
        "route_name": route["route_name"],
        "from": route["stops"][start_index],
        "to": route["stops"][end_index],
        "stops": route["stops"][start_index : end_index + 1],
    }


def find_direct_routes(start: str, end: str, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every forward-only journey on a single route."""
    results: list[dict[str, Any]] = []
    seen: set[tuple[Any, tuple[str, ...]]] = set()

    for route in routes:
        stops = route["normalized_stops"]
        for start_index, stop in enumerate(stops):
            if stop != start:
                continue
            for end_index in range(start_index + 1, len(stops)):
                if stops[end_index] != end:
                    continue
                segment = _route_segment(route, start_index, end_index)
                key = (route["route_id"], tuple(normalize_place(s) for s in segment["stops"]))
                if key not in seen:
                    seen.add(key)
                    results.append({"routes": [segment], "stops": segment["stops"]})
    return results


def find_connected_routes(
    start: str,
    end: str,
    routes: list[dict[str, Any]],
    max_hops: int = 4,
) -> list[dict[str, Any]]:
    """Find forward-only connected journeys with BFS and loop prevention.

    A state represents the passenger's current stop. Each unused route that
    contains that stop can be boarded, and every later stop on that route is
    explored as a possible destination or transfer. Only stops actually
    travelled through are marked visited; future stops on a route are not
    prematurely marked as visited.
    """
    if max_hops < 1:
        return []

    queue = deque([{
        "current": start,
        "stops": [start],
        "normalized_path": [start],
        "segments": [],
        "used_routes": frozenset(),
        "visited_places": frozenset({start}),
    }])
    results: list[dict[str, Any]] = []
    seen_results: set[tuple[Any, ...]] = set()

    while queue:
        state = queue.popleft()
        if len(state["segments"]) >= max_hops:
            continue

        current = state["current"]
        for route in routes:
            route_id = route["route_id"]
            if route_id in state["used_routes"]:
                continue

            route_stops = route["normalized_stops"]
            for board_index, board_stop in enumerate(route_stops):
                if board_stop != current:
                    continue

                # Explore every later stop on this route as a transfer or end.
                for alight_index in range(board_index + 1, len(route_stops)):
                    next_place = route_stops[alight_index]
                    segment_normalized = route_stops[board_index : alight_index + 1]
                    segment_display = route["stops"][board_index : alight_index + 1]
                    # Repeated places within the new segment, or places already
                    # visited earlier in the journey, would create a loop.
                    if any(p in state["visited_places"] for p in segment_normalized[1:]):
                        continue
                    if len(set(segment_normalized)) != len(segment_normalized):
                        continue

                    segment = _route_segment(route, board_index, alight_index)
                    new_segments = state["segments"] + [segment]
                    if state["segments"]:
                        new_stops = state["stops"] + segment_display[1:]
                    else:
                        # Preserve the database's display spelling for the start.
                        new_stops = segment_display.copy()
                    new_path = state["normalized_path"] + segment_normalized[1:]

                    if next_place == end:
                        key = (
                            tuple(s["route_id"] for s in new_segments),
                            tuple(new_path),
                        )
                        if key not in seen_results:
                            seen_results.add(key)
                            results.append({"routes": new_segments, "stops": new_stops})
                        # Reaching the destination ends this journey.
                        continue

                    # A transfer state is queued at each later stop. It will
                    # explore routes that depart from that exact stop.
                    queue.append({
                        "current": next_place,
                        "stops": new_stops,
                        "normalized_path": new_path,
                        "segments": new_segments,
                        "used_routes": state["used_routes"] | {route_id},
                        "visited_places": state["visited_places"] | frozenset(segment_normalized[1:]),
                    })

    return results


def find_routes(start: str, end: str, max_hops: int | None = None) -> dict[str, Any]:
    routes = load_routes()
    hop_limit = max_hops if max_hops is not None else settings.max_route_hops

    if not routes:
        return {"status": "no_data", "message": "No bus route data is currently available.", "routes": []}

    place_index = build_place_index(routes)
    start_match = resolve_place(start, place_index)
    end_match = resolve_place(end, place_index)

    if not start_match["matched"]:
        return {"status": "place_not_found", "message": f"Starting place '{start}' was not found in the route data.", "start_match": start_match, "end_match": end_match, "routes": []}
    if not end_match["matched"]:
        return {"status": "place_not_found", "message": f"Destination '{end}' was not found in the route data.", "start_match": start_match, "end_match": end_match, "routes": []}

    start_normalized = start_match["normalized"]
    end_normalized = end_match["normalized"]
    if start_normalized == end_normalized:
        return {"status": "same_place", "message": "Starting place and destination are the same.", "start_match": start_match, "end_match": end_match, "routes": []}

    direct = find_direct_routes(start_normalized, end_normalized, routes)
    if direct:
        found, status = direct, "direct"
    else:
        found = find_connected_routes(start_normalized, end_normalized, routes, max_hops=hop_limit)
        status = "connected" if found else "not_found"

    # Keep the tool output bounded; the agent is instructed to present only
    # two or three useful options in natural language.
    found = found[: settings.max_route_results]
    return {
        "status": status,
        "message": "Route options found." if found else "No valid forward bus connection was found.",
        "start_match": start_match,
        "end_match": end_match,
        "routes": found,
    }


def bus_route_finder(
    start: str,
    end: str,
    requested_time: str | None = None,
    requested_time_explicit: bool = False,
) -> dict[str, Any]:
    """Function exposed to the agent's tool-calling interface."""
    result = find_routes(start, end)
    for option in result.get("routes", []):
        legs = option.get("routes") or []
        if not legs:
            option["schedule"] = {
                "status": "unavailable",
                "message": "The schedule time could not be found in the database.",
            }
            continue
        first_leg = legs[0]
        try:
            option["schedule"] = lookup_schedule(
                route_id=first_leg["route_id"],
                boarding_stop=first_leg["from"],
                requested_time=requested_time,
                requested_time_explicit=requested_time_explicit,
            )
        except Exception:
            option["schedule"] = {
                "status": "unavailable",
                "message": "The schedule time could not be found in the database.",
            }
    return result
