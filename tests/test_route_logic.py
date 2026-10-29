from app.tools.bus_route_tool import (
    find_connected_routes,
    find_direct_routes,
    normalize_place,
    resolve_place,
    build_place_index,
)


def make_routes():
    raw = [
        {"route_id": 1, "route_name": "A to B", "stops": ["A", "B"]},
        {"route_id": 2, "route_name": "B to C", "stops": ["B", "C"]},
        {"route_id": 3, "route_name": "C to D", "stops": ["C", "D"]},
        {"route_id": 4, "route_name": "B to D alternate", "stops": ["B", "X", "D"]},
        {"route_id": 5, "route_name": "D to A reverse", "stops": ["D", "A"]},
    ]
    for route in raw:
        route["normalized_stops"] = [normalize_place(s) for s in route["stops"]]
    return raw


def test_direct_route():
    routes = make_routes()
    result = find_direct_routes("a", "b", routes)
    assert len(result) == 1
    assert result[0]["stops"] == ["A", "B"]


def test_connected_route_supports_three_routes():
    routes = make_routes()
    result = find_connected_routes("a", "d", routes, max_hops=4)
    assert result
    stop_paths = [r["stops"] for r in result]
    assert ["A", "B", "C", "D"] in stop_paths
    assert ["A", "B", "X", "D"] in stop_paths


def test_no_reverse_direction_when_only_reverse_route_exists():
    routes = [{"route_id": 5, "route_name": "D to A", "stops": ["D", "A"], "normalized_stops": ["d", "a"]}]
    assert find_direct_routes("a", "d", routes) == []
    assert find_connected_routes("a", "d", routes, max_hops=3) == []


def test_does_not_revisit_places_or_reuse_route():
    routes = [
        {"route_id": 1, "route_name": "A-B-C", "stops": ["A", "B", "C"], "normalized_stops": ["a", "b", "c"]},
        {"route_id": 2, "route_name": "C-B", "stops": ["C", "B"], "normalized_stops": ["c", "b"]},
    ]
    result = find_connected_routes("a", "d", routes, max_hops=4)
    assert result == []


def test_alias_uses_spelling_in_database():
    index = build_place_index([{"stops": ["Kozhikode"]}])
    match = resolve_place("Calicut", index)
    assert match["matched"] == "Kozhikode"
    assert match["method"] == "alias"
