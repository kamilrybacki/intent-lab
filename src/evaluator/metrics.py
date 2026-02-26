"""Metric definitions, extraction, and action categorisation."""

from __future__ import annotations

from collections import Counter


# (display_label, dict_key, path_into_stats_json)
METRIC_DEFS: list[tuple[str, str, list[str]]] = [
    ("Population",        "population",       ["population"]),
    ("City Score",        "score",            ["score"]),
    ("Approval (%)",      "approval",         ["evaluation", "approval"]),
    ("Crime Avg",         "crime",            ["census", "crimeAverage"]),
    ("Pollution Avg",     "pollution",        ["census", "pollutionAverage"]),
    ("Land Value Avg",    "land_value",       ["census", "landValueAverage"]),
    ("Funds ($)",         "funds",            ["funds"]),
    ("Tax Rate (%)",      "tax_rate",         ["budget", "taxRate"]),
    ("Cash Flow",         "cash_flow",        ["budget", "cashFlow"]),
    ("Powered Zones",     "powered_zones",    ["census", "poweredZoneCount"]),
    ("Unpowered Zones",   "unpowered_zones",  ["census", "unpoweredZoneCount"]),
    ("Residential Pop",   "res_pop",          ["census", "resPop"]),
    ("Commercial Pop",    "com_pop",          ["census", "comPop"]),
    ("Industrial Pop",    "ind_pop",          ["census", "indPop"]),
    ("Police Stations",   "police_stations",  ["census", "policeStationPop"]),
    ("Fire Stations",     "fire_stations",    ["census", "fireStationPop"]),
    ("Road Tiles",        "road_tiles",       ["census", "roadTotal"]),
]


def extract_metrics(city_data: dict) -> dict[str, float | int]:
    """Pull numeric metrics from collected city data."""
    stats = city_data.get("stats", {})
    result: dict[str, float | int] = {}
    for _, key, path in METRIC_DEFS:
        obj = stats
        for p in path:
            obj = obj.get(p, {}) if isinstance(obj, dict) else 0
        result[key] = obj if isinstance(obj, (int, float)) else 0
    result["total_actions"] = len(city_data.get("actions", []))
    return result


def categorize_actions(
    actions: list[dict],
) -> tuple[Counter, dict[str, int], int]:
    """Categorise actions into types and spending buckets.

    Returns ``(type_counts, spend_by_category, failure_count)``.
    """
    type_counts: Counter = Counter()
    spend: dict[str, int] = {}
    failures = 0

    for act in actions:
        atype = act.get("action_type", "unknown")
        type_counts[atype] += 1
        cost = act.get("cost", 0) or 0

        if "zone" in atype:
            cat = "Zoning"
        elif "road" in atype or "rail" in atype:
            cat = "Transport"
        elif "power" in atype or "wire" in atype:
            cat = "Power/Utility"
        elif atype in (
            "build_fire_station",
            "build_police_station",
            "build_park",
        ):
            cat = "Services"
        elif atype in ("build_seaport", "build_airport", "build_stadium"):
            cat = "Special"
        elif atype == "bulldoze":
            cat = "Demolition"
        elif atype == "advance":
            cat = "Time Advance"
        else:
            cat = "Other"

        spend[cat] = spend.get(cat, 0) + cost
        if act.get("result", "success") != "success":
            failures += 1

    return type_counts, spend, failures
