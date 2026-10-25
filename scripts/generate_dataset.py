"""Deterministic Multi-Profile Dataset Generator for Nova Air (AirCrewOps).

Generates synthetic aviation datasets for:
1. `test`: Compact dataset for fast unit, integration, and disruption tests (data/test/).
2. `demo`: Showcase 48h operational schedule for OCC dashboard and disruption testing (data/demo/ and data/).
3. `benchmark`: Scalable inputs (100, 500, 1000, 2500 legs) for ADS benchmarks (benchmarks/generated/).
"""

from __future__ import annotations

import argparse
import csv
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_EPOCH = 1774915200  # 2026-03-31 00:00:00 UTC anchor

ALL_AIRPORTS: List[Dict[str, Any]] = [
    {
        "code": "BOM",
        "name": "Chhatrapati Shivaji Maharaj International Airport",
        "city": "Mumbai",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 19.0896,
        "longitude": 72.8656,
        "is_hub": True,
        "curfew_start_hour_utc": None,
        "curfew_end_hour_utc": None,
    },
    {
        "code": "DEL",
        "name": "Indira Gandhi International Airport",
        "city": "New Delhi",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 28.5562,
        "longitude": 77.1000,
        "is_hub": True,
        "curfew_start_hour_utc": None,
        "curfew_end_hour_utc": None,
    },
    {
        "code": "BLR",
        "name": "Kempegowda International Airport",
        "city": "Bengaluru",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 13.1986,
        "longitude": 77.7066,
        "is_hub": True,
        "curfew_start_hour_utc": None,
        "curfew_end_hour_utc": None,
    },
    {
        "code": "HYD",
        "name": "Rajiv Gandhi International Airport",
        "city": "Hyderabad",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 17.2403,
        "longitude": 78.4294,
        "is_hub": False,
        "curfew_start_hour_utc": None,
        "curfew_end_hour_utc": None,
    },
    {
        "code": "MAA",
        "name": "Chennai International Airport",
        "city": "Chennai",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 12.9941,
        "longitude": 80.1709,
        "is_hub": False,
        "curfew_start_hour_utc": None,
        "curfew_end_hour_utc": None,
    },
    {
        "code": "CCU",
        "name": "Netaji Subhash Chandra Bose International Airport",
        "city": "Kolkata",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 22.6547,
        "longitude": 88.4467,
        "is_hub": False,
        "curfew_start_hour_utc": None,
        "curfew_end_hour_utc": None,
    },
    {
        "code": "GOI",
        "name": "Dabolim Airport",
        "city": "Goa",
        "country": "India",
        "timezone_offset_seconds": 19800,
        "latitude": 15.3808,
        "longitude": 73.8314,
        "is_hub": False,
        "curfew_start_hour_utc": 18,  # Curfew midnight local (18:30 UTC to 23:30 UTC)
        "curfew_end_hour_utc": 23,
    },
]

ALL_AIRCRAFT: List[Dict[str, Any]] = [
    {"tail_number": "VT-NVA", "aircraft_type": "A320", "home_base": "BOM", "seating_capacity": 180, "total_flight_hours": 2100.0, "is_active": True},
    {"tail_number": "VT-NVB", "aircraft_type": "A320", "home_base": "DEL", "seating_capacity": 180, "total_flight_hours": 1850.5, "is_active": True},
    {"tail_number": "VT-NVC", "aircraft_type": "A320", "home_base": "BLR", "seating_capacity": 180, "total_flight_hours": 1220.0, "is_active": True},
    {"tail_number": "VT-NVD", "aircraft_type": "A320", "home_base": "BOM", "seating_capacity": 180, "total_flight_hours": 940.0, "is_active": True},
    {"tail_number": "VT-NVE", "aircraft_type": "ATR72", "home_base": "BOM", "seating_capacity": 72, "total_flight_hours": 1450.0, "is_active": True},
    {"tail_number": "VT-NVF", "aircraft_type": "ATR72", "home_base": "HYD", "seating_capacity": 72, "total_flight_hours": 1100.0, "is_active": True},
    {"tail_number": "VT-NVG", "aircraft_type": "ATR72", "home_base": "BLR", "seating_capacity": 72, "total_flight_hours": 830.0, "is_active": True},
    {"tail_number": "VT-NVH", "aircraft_type": "ATR72", "home_base": "MAA", "seating_capacity": 72, "total_flight_hours": 600.0, "is_active": True},
]


def write_csv(filepath: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            clean_row = {}
            for k in fieldnames:
                v = row.get(k)
                if v is None:
                    clean_row[k] = ""
                elif isinstance(v, bool):
                    clean_row[k] = "true" if v else "false"
                elif isinstance(v, list):
                    clean_row[k] = ";".join(str(item) for item in v)
                else:
                    clean_row[k] = str(v)
            writer.writerow(clean_row)


def generate_test_profile(seed: int = 42) -> Tuple[List[Dict[str, Any]], ...]:
    random.seed(seed)
    # 5 airports
    airports = [a for a in ALL_AIRPORTS if a["code"] in {"BOM", "DEL", "BLR", "HYD", "CCU"}]

    # 4 aircraft
    aircraft = [
        {"tail_number": "VT-NVA", "aircraft_type": "A320", "home_base": "BOM", "seating_capacity": 180, "total_flight_hours": 1200.0, "is_active": True},
        {"tail_number": "VT-NVB", "aircraft_type": "A320", "home_base": "DEL", "seating_capacity": 180, "total_flight_hours": 980.0, "is_active": True},
        {"tail_number": "VT-NVE", "aircraft_type": "ATR72", "home_base": "BOM", "seating_capacity": 72, "total_flight_hours": 640.0, "is_active": True},
        {"tail_number": "VT-NVF", "aircraft_type": "ATR72", "home_base": "HYD", "seating_capacity": 72, "total_flight_hours": 510.0, "is_active": True},
    ]

    # Maintenance
    maintenance = [
        {
            "id": "MNT-TEST-01",
            "aircraft_tail": "VT-NVA",
            "airport_code": "BOM",
            "start_utc": BASE_EPOCH + 18 * 3600,
            "end_utc": BASE_EPOCH + 22 * 3600,
            "description": "A-Check inspection",
        }
    ]

    # 12 Flight Crew (6 Captains, 6 First Officers) + 10 Cabin Crew = 22 total
    crew = []
    qualifications = []

    # Captains
    for i in range(1, 7):
        cid = f"CRW-CPT-{i:02d}"
        role = "CAPTAIN"
        base = "BOM" if i % 2 == 1 else "DEL"
        curr = base
        # CRW-CPT-05 has expired qualification for A320 testing
        exp = BASE_EPOCH - 86400 if i == 5 else BASE_EPOCH + 365 * 86400
        crew.append({
            "id": cid,
            "name": f"Captain Pilot {i}",
            "role": role,
            "home_base": base,
            "current_airport": curr,
            "cumulative_flight_seconds_7d": 36000,
            "cumulative_duty_seconds_7d": 72000,
            "last_duty_end_utc": BASE_EPOCH - 86400,
            "is_active": True,
        })
        qualifications.append({"crew_id": cid, "aircraft_type": "A320", "valid_until_utc": exp})
        if i in {3, 6}:
            qualifications.append({"crew_id": cid, "aircraft_type": "ATR72", "valid_until_utc": BASE_EPOCH + 365 * 86400})

    # First Officers
    for i in range(1, 7):
        cid = f"CRW-FO-{i:02d}"
        role = "FIRST_OFFICER"
        base = "BOM" if i % 2 == 1 else "BLR"
        curr = base
        # CRW-FO-06 has expired ATR72 qualification
        exp_atr = BASE_EPOCH - 3600 if i == 6 else BASE_EPOCH + 365 * 86400
        crew.append({
            "id": cid,
            "name": f"First Officer {i}",
            "role": role,
            "home_base": base,
            "current_airport": curr,
            "cumulative_flight_seconds_7d": 28800,
            "cumulative_duty_seconds_7d": 54000,
            "last_duty_end_utc": BASE_EPOCH - 86400,
            "is_active": True,
        })
        qualifications.append({"crew_id": cid, "aircraft_type": "A320", "valid_until_utc": BASE_EPOCH + 365 * 86400})
        qualifications.append({"crew_id": cid, "aircraft_type": "ATR72", "valid_until_utc": exp_atr})

    # Cabin Crew (10)
    for i in range(1, 11):
        cid = f"CRW-CAB-{i:02d}"
        base = "BOM" if i <= 5 else "DEL"
        crew.append({
            "id": cid,
            "name": f"Cabin Crew Member {i}",
            "role": "CABIN_CREW",
            "home_base": base,
            "current_airport": base,
            "cumulative_flight_seconds_7d": 32000,
            "cumulative_duty_seconds_7d": 64000,
            "last_duty_end_utc": BASE_EPOCH - 86400,
            "is_active": True,
        })
        qualifications.append({"crew_id": cid, "aircraft_type": "A320", "valid_until_utc": BASE_EPOCH + 365 * 86400})
        qualifications.append({"crew_id": cid, "aircraft_type": "ATR72", "valid_until_utc": BASE_EPOCH + 365 * 86400})

    # Special positioning test: CRW-CPT-04 current_airport is HYD while home_base is DEL
    for c in crew:
        if c["id"] == "CRW-CPT-04":
            c["current_airport"] = "HYD"

    # 14 Flights over 24h
    flights = [
        # Multi-leg sequence: NV-101 followed by NV-102
        {"flight_number": "NV-101", "origin": "BOM", "destination": "DEL", "departure_utc": BASE_EPOCH + 6 * 3600, "arrival_utc": BASE_EPOCH + 8 * 3600 + 7200 // 2, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-102", "origin": "DEL", "destination": "BLR", "departure_utc": BASE_EPOCH + 10 * 3600, "arrival_utc": BASE_EPOCH + 13 * 3600, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-103", "origin": "BLR", "destination": "BOM", "departure_utc": BASE_EPOCH + 14 * 3600, "arrival_utc": BASE_EPOCH + 16 * 3600, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-104", "origin": "DEL", "destination": "BOM", "departure_utc": BASE_EPOCH + 7 * 3600, "arrival_utc": BASE_EPOCH + 9 * 3600 + 1800, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-105", "origin": "BOM", "destination": "CCU", "departure_utc": BASE_EPOCH + 11 * 3600, "arrival_utc": BASE_EPOCH + 13 * 3600 + 5400, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-106", "origin": "CCU", "destination": "DEL", "departure_utc": BASE_EPOCH + 16 * 3600, "arrival_utc": BASE_EPOCH + 18 * 3600 + 3600, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        # ATR72 regional legs
        {"flight_number": "NV-107", "origin": "BOM", "destination": "HYD", "departure_utc": BASE_EPOCH + 6 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 8 * 3600, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-108", "origin": "HYD", "destination": "BLR", "departure_utc": BASE_EPOCH + 9 * 3600, "arrival_utc": BASE_EPOCH + 10 * 3600 + 1800, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-109", "origin": "BLR", "destination": "HYD", "departure_utc": BASE_EPOCH + 12 * 3600, "arrival_utc": BASE_EPOCH + 13 * 3600 + 1800, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-110", "origin": "HYD", "destination": "BOM", "departure_utc": BASE_EPOCH + 15 * 3600, "arrival_utc": BASE_EPOCH + 16 * 3600 + 3600, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        # Second ATR tail
        {"flight_number": "NV-111", "origin": "HYD", "destination": "CCU", "departure_utc": BASE_EPOCH + 7 * 3600, "arrival_utc": BASE_EPOCH + 9 * 3600 + 3600, "aircraft_tail": "VT-NVF", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-112", "origin": "CCU", "destination": "HYD", "departure_utc": BASE_EPOCH + 11 * 3600, "arrival_utc": BASE_EPOCH + 13 * 3600 + 3600, "aircraft_tail": "VT-NVF", "required_aircraft_type": "ATR72"},
        # Positioning leg candidate
        {"flight_number": "NV-113", "origin": "HYD", "destination": "DEL", "departure_utc": BASE_EPOCH + 8 * 3600, "arrival_utc": BASE_EPOCH + 10 * 3600 + 1800, "aircraft_tail": None, "required_aircraft_type": "A320"},
        # 1 deliberately uncoverable regional leg (isolated timeframe, impossible crew rest / aircraft clash)
        {"flight_number": "NV-114", "origin": "CCU", "destination": "BOM", "departure_utc": BASE_EPOCH + 23 * 3600, "arrival_utc": BASE_EPOCH + 25 * 3600 + 1800, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
    ]

    # Duty History (sample prior duty records)
    duty_history = [
        {
            "id": "DUTY-TEST-01",
            "crew_id": "CRW-CPT-01",
            "flight_leg_ids": ["NV-PREV-01"],
            "report_utc": BASE_EPOCH - 86400 + 8 * 3600,
            "release_utc": BASE_EPOCH - 86400 + 14 * 3600,
            "duty_type": "FLIGHT_DUTY",
            "total_flight_seconds": 18000,
        }
    ]

    return airports, aircraft, maintenance, crew, qualifications, flights, duty_history


def generate_demo_profile(seed: int = 42) -> Tuple[List[Dict[str, Any]], ...]:
    random.seed(seed)
    airports = list(ALL_AIRPORTS)
    aircraft = list(ALL_AIRCRAFT)

    maintenance = [
        {
            "id": "MNT-DEMO-01",
            "aircraft_tail": "VT-NVA",
            "airport_code": "BOM",
            "start_utc": BASE_EPOCH + 20 * 3600,
            "end_utc": BASE_EPOCH + 25 * 3600,
            "description": "Scheduled overnight avionics check",
        },
        {
            "id": "MNT-DEMO-02",
            "aircraft_tail": "VT-NVE",
            "airport_code": "HYD",
            "start_utc": BASE_EPOCH + 40 * 3600,
            "end_utc": BASE_EPOCH + 45 * 3600,
            "description": "Turboprop engine 100-hour inspection",
        },
    ]

    # 22 Flight Crew (11 Captains, 11 First Officers) + 20 Cabin Crew = 42 total
    crew = []
    qualifications = []

    captains = [
        ("CRW-CPT-01", "Capt. Vikram Malhotra", "BOM", "BOM", ["A320"]),
        ("CRW-CPT-02", "Capt. Rajesh Sharma", "DEL", "DEL", ["A320"]),
        ("CRW-CPT-03", "Capt. Ananya Iyer", "BLR", "BLR", ["A320"]),
        ("CRW-CPT-04", "Capt. Siddharth Rao", "HYD", "HYD", ["ATR72"]),
        ("CRW-CPT-05", "Capt. Priya Nair", "BOM", "BOM", ["A320", "ATR72"]),
        ("CRW-CPT-06", "Capt. Rohan Deshmukh", "DEL", "DEL", ["A320"]),
        ("CRW-CPT-07", "Capt. Meera Kulkarni", "MAA", "MAA", ["ATR72"]),
        ("CRW-CPT-08", "Capt. Arjun Kapoor", "BLR", "BLR", ["A320", "ATR72"]),
        ("CRW-CPT-09", "Capt. Sunita Sen", "CCU", "CCU", ["A320"]),
        ("CRW-CPT-10", "Capt. Devendra Joshi", "BOM", "GOI", ["A320"]),  # Out of base for Dijkstra positioning
        ("CRW-CPT-11", "Capt. Neha Banerjee", "DEL", "DEL", ["A320"]),
    ]

    for cid, name, base, curr, ratings in captains:
        crew.append({
            "id": cid,
            "name": name,
            "role": "CAPTAIN",
            "home_base": base,
            "current_airport": curr,
            "cumulative_flight_seconds_7d": 72000 if cid == "CRW-CPT-11" else 36000,
            "cumulative_duty_seconds_7d": 144000 if cid == "CRW-CPT-11" else 72000,
            "last_duty_end_utc": BASE_EPOCH - 43200,
            "is_active": True,
        })
        for r in ratings:
            qualifications.append({"crew_id": cid, "aircraft_type": r, "valid_until_utc": BASE_EPOCH + 365 * 86400})

    first_officers = [
        ("CRW-FO-01", "FO Amit Verma", "BOM", "BOM", ["A320"]),
        ("CRW-FO-02", "FO Divya Pillai", "DEL", "DEL", ["A320"]),
        ("CRW-FO-03", "FO Karan Mehta", "BLR", "BLR", ["A320"]),
        ("CRW-FO-04", "FO Sneha Reddy", "HYD", "HYD", ["ATR72"]),
        ("CRW-FO-05", "FO Varun Bhatia", "BOM", "BOM", ["A320", "ATR72"]),
        ("CRW-FO-06", "FO Pooja Hegde", "DEL", "DEL", ["A320"]),
        ("CRW-FO-07", "FO Nikhil Thomas", "MAA", "MAA", ["ATR72"]),
        ("CRW-FO-08", "FO Shreya Das", "CCU", "CCU", ["A320"]),
        ("CRW-FO-09", "FO Aditya Saxena", "BLR", "BLR", ["A320", "ATR72"]),
        ("CRW-FO-10", "FO Kavita Menon", "BOM", "BOM", ["A320"]),
        ("CRW-FO-11", "FO Rakesh Patel", "DEL", "DEL", ["A320"]),
    ]

    for cid, name, base, curr, ratings in first_officers:
        crew.append({
            "id": cid,
            "name": name,
            "role": "FIRST_OFFICER",
            "home_base": base,
            "current_airport": curr,
            "cumulative_flight_seconds_7d": 28800,
            "cumulative_duty_seconds_7d": 60000,
            "last_duty_end_utc": BASE_EPOCH - 43200,
            "is_active": True,
        })
        for r in ratings:
            qualifications.append({"crew_id": cid, "aircraft_type": r, "valid_until_utc": BASE_EPOCH + 365 * 86400})

    # 20 Cabin Crew
    cabin_crew_names = [
        "Aarav Shah", "Aditi Rao", "Alok Kumar", "Ananya Sen", "Deepak Verma",
        "Geeta Iyer", "Harish Nair", "Ishita Roy", "Jatin Solanki", "Kiran Gill",
        "Lata Mangesh", "Manish Paul", "Nandini Ghosh", "Pavan Chawla", "Radha Dixit",
        "Sameer Khan", "Tanya Sethi", "Umesh Yadav", "Vidya Balan", "Zoya Akhtar"
    ]

    bases = ["BOM", "DEL", "BLR", "HYD", "MAA"]
    for i, name in enumerate(cabin_crew_names, start=1):
        cid = f"CRW-CAB-{i:02d}"
        base = bases[(i - 1) % len(bases)]
        crew.append({
            "id": cid,
            "name": name,
            "role": "CABIN_CREW",
            "home_base": base,
            "current_airport": base,
            "cumulative_flight_seconds_7d": 36000,
            "cumulative_duty_seconds_7d": 72000,
            "last_duty_end_utc": BASE_EPOCH - 43200,
            "is_active": True,
        })
        qualifications.append({"crew_id": cid, "aircraft_type": "A320", "valid_until_utc": BASE_EPOCH + 365 * 86400})
        qualifications.append({"crew_id": cid, "aircraft_type": "ATR72", "valid_until_utc": BASE_EPOCH + 365 * 86400})

    # 36 Flight Legs across 48h (NV-101 to NV-136)
    flights = [
        # Day 1: Main trunk routes (A320)
        {"flight_number": "NV-101", "origin": "BOM", "destination": "DEL", "departure_utc": BASE_EPOCH + 6 * 3600, "arrival_utc": BASE_EPOCH + 8 * 3600 + 1200, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-102", "origin": "DEL", "destination": "BOM", "departure_utc": BASE_EPOCH + 9 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 11 * 3600 + 3000, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-103", "origin": "BOM", "destination": "BLR", "departure_utc": BASE_EPOCH + 13 * 3600, "arrival_utc": BASE_EPOCH + 14 * 3600 + 2700, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-104", "origin": "BLR", "destination": "BOM", "departure_utc": BASE_EPOCH + 16 * 3600, "arrival_utc": BASE_EPOCH + 17 * 3600 + 2700, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},

        {"flight_number": "NV-105", "origin": "DEL", "destination": "BLR", "departure_utc": BASE_EPOCH + 6 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 9 * 3600 + 1800, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-106", "origin": "BLR", "destination": "DEL", "departure_utc": BASE_EPOCH + 10 * 3600 + 2700, "arrival_utc": BASE_EPOCH + 13 * 3600 + 2700, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-107", "origin": "DEL", "destination": "CCU", "departure_utc": BASE_EPOCH + 15 * 3600, "arrival_utc": BASE_EPOCH + 17 * 3600 + 1200, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-108", "origin": "CCU", "destination": "DEL", "departure_utc": BASE_EPOCH + 18 * 3600 + 2700, "arrival_utc": BASE_EPOCH + 21 * 3600, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},

        {"flight_number": "NV-109", "origin": "BLR", "destination": "MAA", "departure_utc": BASE_EPOCH + 7 * 3600, "arrival_utc": BASE_EPOCH + 8 * 3600, "aircraft_tail": "VT-NVC", "required_aircraft_type": "A320"},
        {"flight_number": "NV-110", "origin": "MAA", "destination": "CCU", "departure_utc": BASE_EPOCH + 9 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 11 * 3600 + 3600, "aircraft_tail": "VT-NVC", "required_aircraft_type": "A320"},
        {"flight_number": "NV-111", "origin": "CCU", "destination": "MAA", "departure_utc": BASE_EPOCH + 13 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 16 * 3600, "aircraft_tail": "VT-NVC", "required_aircraft_type": "A320"},
        {"flight_number": "NV-112", "origin": "MAA", "destination": "BLR", "departure_utc": BASE_EPOCH + 17 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 18 * 3600 + 1800, "aircraft_tail": "VT-NVC", "required_aircraft_type": "A320"},

        {"flight_number": "NV-113", "origin": "BOM", "destination": "GOI", "departure_utc": BASE_EPOCH + 8 * 3600, "arrival_utc": BASE_EPOCH + 9 * 3600 + 600, "aircraft_tail": "VT-NVD", "required_aircraft_type": "A320"},
        {"flight_number": "NV-114", "origin": "GOI", "destination": "BOM", "departure_utc": BASE_EPOCH + 10 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 11 * 3600 + 2400, "aircraft_tail": "VT-NVD", "required_aircraft_type": "A320"},
        {"flight_number": "NV-115", "origin": "BOM", "destination": "HYD", "departure_utc": BASE_EPOCH + 13 * 3600, "arrival_utc": BASE_EPOCH + 14 * 3600 + 1800, "aircraft_tail": "VT-NVD", "required_aircraft_type": "A320"},
        {"flight_number": "NV-116", "origin": "HYD", "destination": "BOM", "departure_utc": BASE_EPOCH + 15 * 3600 + 2700, "arrival_utc": BASE_EPOCH + 17 * 3600 + 900, "aircraft_tail": "VT-NVD", "required_aircraft_type": "A320"},

        # ATR72 Regional hops (Day 1)
        {"flight_number": "NV-117", "origin": "BOM", "destination": "GOI", "departure_utc": BASE_EPOCH + 6 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 7 * 3600 + 4500, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-118", "origin": "GOI", "destination": "BOM", "departure_utc": BASE_EPOCH + 9 * 3600, "arrival_utc": BASE_EPOCH + 10 * 3600 + 2700, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-119", "origin": "HYD", "destination": "MAA", "departure_utc": BASE_EPOCH + 7 * 3600, "arrival_utc": BASE_EPOCH + 8 * 3600 + 1800, "aircraft_tail": "VT-NVF", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-120", "origin": "MAA", "destination": "HYD", "departure_utc": BASE_EPOCH + 9 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 10 * 3600 + 3600, "aircraft_tail": "VT-NVF", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-121", "origin": "BLR", "destination": "HYD", "departure_utc": BASE_EPOCH + 8 * 3600, "arrival_utc": BASE_EPOCH + 9 * 3600 + 1800, "aircraft_tail": "VT-NVG", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-122", "origin": "HYD", "destination": "BLR", "departure_utc": BASE_EPOCH + 10 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 11 * 3600 + 3600, "aircraft_tail": "VT-NVG", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-123", "origin": "MAA", "destination": "BLR", "departure_utc": BASE_EPOCH + 11 * 3600, "arrival_utc": BASE_EPOCH + 12 * 3600 + 900, "aircraft_tail": "VT-NVH", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-124", "origin": "BLR", "destination": "MAA", "departure_utc": BASE_EPOCH + 13 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 14 * 3600 + 2700, "aircraft_tail": "VT-NVH", "required_aircraft_type": "ATR72"},

        # Day 2: Network rotations (Hours 24 to 48)
        {"flight_number": "NV-125", "origin": "BOM", "destination": "DEL", "departure_utc": BASE_EPOCH + 30 * 3600, "arrival_utc": BASE_EPOCH + 32 * 3600 + 1200, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-126", "origin": "DEL", "destination": "BOM", "departure_utc": BASE_EPOCH + 33 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 35 * 3600 + 3000, "aircraft_tail": "VT-NVA", "required_aircraft_type": "A320"},
        {"flight_number": "NV-127", "origin": "DEL", "destination": "CCU", "departure_utc": BASE_EPOCH + 29 * 3600, "arrival_utc": BASE_EPOCH + 31 * 3600 + 1200, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-128", "origin": "CCU", "destination": "DEL", "departure_utc": BASE_EPOCH + 32 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 34 * 3600 + 3000, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        {"flight_number": "NV-129", "origin": "BLR", "destination": "BOM", "departure_utc": BASE_EPOCH + 31 * 3600, "arrival_utc": BASE_EPOCH + 32 * 3600 + 2700, "aircraft_tail": "VT-NVC", "required_aircraft_type": "A320"},
        {"flight_number": "NV-130", "origin": "BOM", "destination": "BLR", "departure_utc": BASE_EPOCH + 34 * 3600, "arrival_utc": BASE_EPOCH + 35 * 3600 + 2700, "aircraft_tail": "VT-NVC", "required_aircraft_type": "A320"},
        {"flight_number": "NV-131", "origin": "BOM", "destination": "MAA", "departure_utc": BASE_EPOCH + 30 * 3600 + 1800, "arrival_utc": BASE_EPOCH + 32 * 3600 + 3600, "aircraft_tail": "VT-NVD", "required_aircraft_type": "A320"},
        {"flight_number": "NV-132", "origin": "MAA", "destination": "BOM", "departure_utc": BASE_EPOCH + 34 * 3600, "arrival_utc": BASE_EPOCH + 36 * 3600 + 1800, "aircraft_tail": "VT-NVD", "required_aircraft_type": "A320"},

        # ATR72 Day 2
        {"flight_number": "NV-133", "origin": "BOM", "destination": "HYD", "departure_utc": BASE_EPOCH + 28 * 3600, "arrival_utc": BASE_EPOCH + 29 * 3600 + 3600, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},
        {"flight_number": "NV-134", "origin": "HYD", "destination": "GOI", "departure_utc": BASE_EPOCH + 31 * 3600, "arrival_utc": BASE_EPOCH + 32 * 3600 + 2700, "aircraft_tail": "VT-NVE", "required_aircraft_type": "ATR72"},

        # 2 Legitimately Constrained / Uncoverable Flights (exceed max duty / curfew clash)
        # NV-135: Curfew breach into GOI during active curfew window (19:00 UTC arrival)
        {"flight_number": "NV-135", "origin": "DEL", "destination": "GOI", "departure_utc": BASE_EPOCH + 17 * 3600, "arrival_utc": BASE_EPOCH + 19 * 3600 + 1800, "aircraft_tail": "VT-NVB", "required_aircraft_type": "A320"},
        # NV-136: Insufficient aircraft TAT turnaround time and crew rest clash at Day 2 end
        {"flight_number": "NV-136", "origin": "CCU", "destination": "GOI", "departure_utc": BASE_EPOCH + 46 * 3600, "arrival_utc": BASE_EPOCH + 49 * 3600, "aircraft_tail": "VT-NVF", "required_aircraft_type": "ATR72"},
    ]

    duty_history = [
        {
            "id": "DUTY-DEMO-01",
            "crew_id": "CRW-CPT-01",
            "flight_leg_ids": ["NV-HIST-01", "NV-HIST-02"],
            "report_utc": BASE_EPOCH - 86400 + 6 * 3600,
            "release_utc": BASE_EPOCH - 86400 + 15 * 3600,
            "duty_type": "FLIGHT_DUTY",
            "total_flight_seconds": 25200,
        },
        {
            "id": "DUTY-DEMO-02",
            "crew_id": "CRW-CPT-11",
            "flight_leg_ids": ["NV-HIST-03", "NV-HIST-04"],
            "report_utc": BASE_EPOCH - 86400 + 8 * 3600,
            "release_utc": BASE_EPOCH - 86400 + 18 * 3600,
            "duty_type": "FLIGHT_DUTY",
            "total_flight_seconds": 28800,
        },
    ]

    return airports, aircraft, maintenance, crew, qualifications, flights, duty_history


def generate_benchmark_profile(scale: int = 500, seed: int = 42) -> Tuple[List[Dict[str, Any]], ...]:
    random.seed(seed)
    airports = list(ALL_AIRPORTS)

    # Scale aircraft: at least 4, roughly scale / 40
    num_aircraft = max(6, scale // 40)
    aircraft = []
    for i in range(1, num_aircraft + 1):
        tail = f"VT-B{i:03d}"
        atype = "A320" if i % 3 != 0 else "ATR72"
        base = airports[(i - 1) % len(airports)]["code"]
        aircraft.append({
            "tail_number": tail,
            "aircraft_type": atype,
            "home_base": base,
            "seating_capacity": 180 if atype == "A320" else 72,
            "total_flight_hours": round(random.uniform(500.0, 3000.0), 1),
            "is_active": True,
        })

    # Scale crew: roughly 3 pilots per aircraft + cabin crew
    crew = []
    qualifications = []
    c_idx = 1
    for ac in aircraft:
        atype = ac["aircraft_type"]
        base = ac["home_base"]
        # 2 Captains per tail
        for _ in range(2):
            cid = f"CRW-CPT-B{c_idx:04d}"
            crew.append({
                "id": cid,
                "name": f"Benchmark Captain {c_idx}",
                "role": "CAPTAIN",
                "home_base": base,
                "current_airport": base,
                "cumulative_flight_seconds_7d": random.randint(10000, 70000),
                "cumulative_duty_seconds_7d": random.randint(20000, 140000),
                "last_duty_end_utc": BASE_EPOCH - 86400,
                "is_active": True,
            })
            qualifications.append({"crew_id": cid, "aircraft_type": atype, "valid_until_utc": BASE_EPOCH + 365 * 86400})
            c_idx += 1

        # 2 FOs per tail
        for _ in range(2):
            cid = f"CRW-FO-B{c_idx:04d}"
            crew.append({
                "id": cid,
                "name": f"Benchmark FO {c_idx}",
                "role": "FIRST_OFFICER",
                "home_base": base,
                "current_airport": base,
                "cumulative_flight_seconds_7d": random.randint(10000, 70000),
                "cumulative_duty_seconds_7d": random.randint(20000, 140000),
                "last_duty_end_utc": BASE_EPOCH - 86400,
                "is_active": True,
            })
            qualifications.append({"crew_id": cid, "aircraft_type": atype, "valid_until_utc": BASE_EPOCH + 365 * 86400})
            c_idx += 1

        # 4 Cabin crew per tail
        for _ in range(4):
            cid = f"CRW-CAB-B{c_idx:04d}"
            crew.append({
                "id": cid,
                "name": f"Benchmark Cabin {c_idx}",
                "role": "CABIN_CREW",
                "home_base": base,
                "current_airport": base,
                "cumulative_flight_seconds_7d": random.randint(10000, 70000),
                "cumulative_duty_seconds_7d": random.randint(20000, 140000),
                "last_duty_end_utc": BASE_EPOCH - 86400,
                "is_active": True,
            })
            qualifications.append({"crew_id": cid, "aircraft_type": atype, "valid_until_utc": BASE_EPOCH + 365 * 86400})
            c_idx += 1

    # Generate synthetic flight legs
    flights = []
    codes = [a["code"] for a in airports]
    current_tail_locs = {ac["tail_number"]: ac["home_base"] for ac in aircraft}
    current_tail_times = {ac["tail_number"]: BASE_EPOCH + random.randint(0, 10800) for ac in aircraft}

    for f_i in range(1, scale + 1):
        ac = aircraft[(f_i - 1) % len(aircraft)]
        tail = ac["tail_number"]
        atype = ac["aircraft_type"]
        origin = current_tail_locs[tail]
        possible_dests = [c for c in codes if c != origin]
        dest = random.choice(possible_dests)
        dep = current_tail_times[tail] + random.randint(2700, 7200)
        dur = random.randint(3600, 10800)
        arr = dep + dur
        current_tail_locs[tail] = dest
        current_tail_times[tail] = arr

        flights.append({
            "flight_number": f"NV-B{f_i:04d}",
            "origin": origin,
            "destination": dest,
            "departure_utc": dep,
            "arrival_utc": arr,
            "aircraft_tail": tail,
            "required_aircraft_type": atype,
        })

    # Sort flights chronologically
    flights.sort(key=lambda x: x["departure_utc"])

    maintenance = []
    for i, ac in enumerate(aircraft[:max(2, len(aircraft) // 5)], start=1):
        m_start = BASE_EPOCH + random.randint(12, 36) * 3600
        maintenance.append({
            "id": f"MNT-B{i:03d}",
            "aircraft_tail": ac["tail_number"],
            "airport_code": ac["home_base"],
            "start_utc": m_start,
            "end_utc": m_start + 4 * 3600,
            "description": "Routine scheduled check",
        })

    duty_history = []
    return airports, aircraft, maintenance, crew, qualifications, flights, duty_history


def save_dataset(output_dir: Path, data: Tuple[List[Dict[str, Any]], ...]) -> Dict[str, int]:
    airports, aircraft, maintenance, crew, qualifications, flights, duty_history = data

    files = {
        "airports.csv": (
            ["code", "name", "city", "country", "timezone_offset_seconds", "latitude", "longitude", "is_hub", "curfew_start_hour_utc", "curfew_end_hour_utc"],
            airports,
        ),
        "aircraft.csv": (
            ["tail_number", "aircraft_type", "home_base", "seating_capacity", "total_flight_hours", "is_active"],
            aircraft,
        ),
        "maintenance.csv": (
            ["id", "aircraft_tail", "airport_code", "start_utc", "end_utc", "description"],
            maintenance,
        ),
        "crew.csv": (
            ["id", "name", "role", "home_base", "current_airport", "cumulative_flight_seconds_7d", "cumulative_duty_seconds_7d", "last_duty_end_utc", "is_active"],
            crew,
        ),
        "qualifications.csv": (
            ["crew_id", "aircraft_type", "valid_until_utc"],
            qualifications,
        ),
        "flights.csv": (
            ["flight_number", "origin", "destination", "departure_utc", "arrival_utc", "aircraft_tail", "required_aircraft_type"],
            flights,
        ),
        "duty_history.csv": (
            ["id", "crew_id", "flight_leg_ids", "report_utc", "release_utc", "duty_type", "total_flight_seconds"],
            duty_history,
        ),
    }

    counts = {}
    for filename, (fieldnames, rows) in files.items():
        write_csv(output_dir / filename, fieldnames, rows)
        counts[filename] = len(rows)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Dataset Generator for Nova Air")
    parser.add_argument("--profile", choices=["test", "demo", "benchmark"], default="demo", help="Profile to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic generation")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory")
    parser.add_argument("--scale", type=int, default=500, help="Number of flight legs for benchmark profile")

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.output_dir:
        out = Path(args.output_dir)
    elif args.profile == "test":
        out = repo_root / "data" / "test"
    elif args.profile == "demo":
        out = repo_root / "data" / "demo"
    else:
        out = repo_root / "benchmarks" / "generated" / f"scale_{args.scale}"

    print(f"Generating '{args.profile}' dataset (seed={args.seed}) to: {out}")

    if args.profile == "test":
        data = generate_test_profile(seed=args.seed)
    elif args.profile == "demo":
        data = generate_demo_profile(seed=args.seed)
    else:
        data = generate_benchmark_profile(scale=args.scale, seed=args.seed)

    counts = save_dataset(out, data)

    # For demo profile, also populate data/ directly as the canonical default dataset
    if args.profile == "demo" and not args.output_dir:
        root_data_dir = repo_root / "data"
        save_dataset(root_data_dir, data)
        print(f"Also synchronized default demo dataset to: {root_data_dir}")

    print("Generation complete. File counts:")
    for fn, count in counts.items():
        print(f"  {fn:20s}: {count} records")


if __name__ == "__main__":
    main()
