"""Unit tests for Nova Air domain models, regulatory profile, and dataset loader."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from pydantic import ValidationError

from backend.app.models.domain import (
    Aircraft,
    Airport,
    CrewMember,
    CrewQualification,
    CrewRole,
    DutyPeriod,
    DutyType,
    FlightLeg,
    MaintenanceWindow,
    PositioningItinerary,
    RosterAssignment,
    RosterStatus,
    RuleSeverity,
    RuleViolation,
)
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.dataset_loader import DatasetLoader, DatasetValidationError
from scripts.generate_dataset import generate_demo_profile, generate_test_profile, save_dataset

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def test_domain_half_open_interval_validation():
    """Verify strict [start_utc, end_utc) half-open interval validation across all domain models."""
    # Valid FlightLeg
    leg = FlightLeg(
        flight_number="NV-101",
        origin="BOM",
        destination="DEL",
        departure_utc=1000,
        arrival_utc=2000,
        required_aircraft_type="A320",
    )
    assert leg.flight_duration_seconds == 1000

    # Inverted flight interval must raise ValueError
    with pytest.raises(ValidationError):
        FlightLeg(
            flight_number="NV-ERR",
            origin="BOM",
            destination="DEL",
            departure_utc=2000,
            arrival_utc=1000,
        )

    # Identical departure and arrival must raise ValueError
    with pytest.raises(ValidationError):
        FlightLeg(
            flight_number="NV-ERR",
            origin="BOM",
            destination="DEL",
            departure_utc=1000,
            arrival_utc=1000,
        )

    # Origin identical to destination must raise ValueError
    with pytest.raises(ValidationError):
        FlightLeg(
            flight_number="NV-ERR",
            origin="BOM",
            destination="BOM",
            departure_utc=1000,
            arrival_utc=2000,
        )

    # Inverted MaintenanceWindow
    with pytest.raises(ValidationError):
        MaintenanceWindow(
            id="MNT-ERR",
            aircraft_tail="VT-NVA",
            airport_code="BOM",
            start_utc=5000,
            end_utc=4000,
        )

    # Inverted DutyPeriod
    with pytest.raises(ValidationError):
        DutyPeriod(
            id="DUTY-ERR",
            crew_id="CRW-01",
            report_utc=8000,
            release_utc=7000,
        )

    # Inverted PositioningItinerary
    with pytest.raises(ValidationError):
        PositioningItinerary(
            crew_id="CRW-01",
            origin="BOM",
            destination="DEL",
            departure_utc=9000,
            arrival_utc=8000,
        )


def test_crew_qualification_check():
    """Verify CrewMember.has_valid_rating correctly respects aircraft type and expiration timestamp."""
    crew = CrewMember(
        id="CRW-CPT-01",
        name="Capt. Vikram",
        role=CrewRole.CAPTAIN,
        home_base="BOM",
        current_airport="BOM",
        qualifications=[
            CrewQualification(aircraft_type="A320", valid_until_utc=2000),
            CrewQualification(aircraft_type="ATR72", valid_until_utc=500),
        ],
    )

    # A320 valid before timestamp 2000
    assert crew.has_valid_rating("A320", at_utc=1500) is True
    assert crew.has_valid_rating("a320", at_utc=1999) is True
    assert crew.has_valid_rating("A320", at_utc=2000) is False  # Expired at boundary
    assert crew.has_valid_rating("A320", at_utc=2500) is False

    # ATR72 expired at timestamp 1000
    assert crew.has_valid_rating("ATR72", at_utc=400) is True
    assert crew.has_valid_rating("ATR72", at_utc=1000) is False

    # Uncertified aircraft type
    assert crew.has_valid_rating("B737", at_utc=1000) is False


def test_rule_profile_loader():
    """Verify nova_air_demo_v1 profile loads correctly and enforces mandatory regulatory thresholds."""
    profile = load_rule_profile("nova_air_demo_v1")
    assert profile.profile_id == "nova_air_demo_v1"
    assert "Nova Air" in profile.airline_name

    # Flight crew limits
    fc = profile.flight_crew_rules
    assert fc.max_daily_flight_time_seconds == 28800  # 8 hours
    assert fc.max_daily_fdp_seconds == 45000         # 12.5 hours
    assert fc.min_inter_duty_rest_seconds == 43200   # 12 hours
    assert fc.report_lead_time_seconds == 3600       # 60 mins
    assert fc.release_buffer_seconds == 1800         # 30 mins
    assert fc.min_connection_time_different_aircraft_seconds == 2400
    assert fc.min_connection_time_same_aircraft_seconds == 1800

    # Turnaround times
    assert profile.aircraft_turnaround_times_seconds["A320"] == 2700
    assert profile.aircraft_turnaround_times_seconds["ATR72"] == 1800

    # Crew complement
    assert profile.crew_complement["A320"]["captains"] == 1
    assert profile.crew_complement["A320"]["first_officers"] == 1
    assert profile.crew_complement["A320"]["cabin_crew"] == 4


def test_dataset_generator_determinism():
    """Verify that running the dataset generator twice with identical seed produces byte-identical files."""
    temp_dir_1 = Path(tempfile.mkdtemp(prefix="nova_air_test1_"))
    temp_dir_2 = Path(tempfile.mkdtemp(prefix="nova_air_test2_"))

    try:
        data1 = generate_test_profile(seed=42)
        save_dataset(temp_dir_1, data1)

        data2 = generate_test_profile(seed=42)
        save_dataset(temp_dir_2, data2)

        csv_files = ["airports.csv", "aircraft.csv", "maintenance.csv", "crew.csv", "qualifications.csv", "flights.csv", "duty_history.csv"]
        for fn in csv_files:
            file1 = temp_dir_1 / fn
            file2 = temp_dir_2 / fn
            assert file1.exists() and file2.exists()
            assert file1.read_bytes() == file2.read_bytes(), f"Deterministic generation mismatch in {fn}"
    finally:
        shutil.rmtree(temp_dir_1, ignore_errors=True)
        shutil.rmtree(temp_dir_2, ignore_errors=True)


def test_demo_dataset_integrity():
    """Verify that default demo dataset in data/ loads without any errors and matches required counts."""
    data_dir = ROOT_DIR / "data"
    loader = DatasetLoader()
    dataset = loader.load_from_directory(data_dir)

    assert len(dataset.airports) == 7
    assert len(dataset.aircraft) == 8
    assert len(dataset.crew) == 42
    assert len(dataset.flights) == 36
    assert len(dataset.maintenance) == 2
    assert len(dataset.duty_history) == 2

    # Verify key airports
    assert "BOM" in dataset.airports
    assert "DEL" in dataset.airports
    assert "GOI" in dataset.airports
    assert dataset.airports["GOI"].curfew_start_hour_utc == 18

    # Verify flight lookups
    f101 = dataset.get_flight("NV-101")
    assert f101 is not None
    assert f101.origin == "BOM"
    assert f101.destination == "DEL"
    assert f101.aircraft_tail == "VT-NVA"


def test_test_dataset_integrity():
    """Verify that test dataset in data/test loads cleanly and has required test scenario features."""
    test_dir = ROOT_DIR / "data" / "test"
    loader = DatasetLoader()
    dataset = loader.load_from_directory(test_dir)

    assert len(dataset.airports) == 5
    assert len(dataset.aircraft) == 4
    assert len(dataset.crew) == 22
    assert len(dataset.flights) == 14
    assert len(dataset.maintenance) == 1
    assert len(dataset.duty_history) == 1

    # Check for expired qualification on CRW-CPT-05
    c5 = dataset.get_crew("CRW-CPT-05")
    assert c5 is not None
    assert c5.has_valid_rating("A320", at_utc=dataset.flights[0].departure_utc) is False

    # Check positioning scenario crew: CRW-CPT-04 at HYD with home_base DEL
    c4 = dataset.get_crew("CRW-CPT-04")
    assert c4 is not None
    assert c4.current_airport == "HYD"
    assert c4.home_base == "DEL"


def test_corrupted_dataset_rejections():
    """Verify DatasetLoader catches invalid foreign keys, invalid intervals, and impossible routes."""
    temp_dir = Path(tempfile.mkdtemp(prefix="nova_air_corrupt_"))
    try:
        # Generate baseline
        data = generate_test_profile(seed=42)
        save_dataset(temp_dir, data)
        loader = DatasetLoader()

        # 1. Unknown foreign key airport in flights.csv
        flights_file = temp_dir / "flights.csv"
        content = flights_file.read_text(encoding="utf-8")
        corrupted_content = content.replace("BOM", "XYZ", 1)
        flights_file.write_text(corrupted_content, encoding="utf-8")

        with pytest.raises(DatasetValidationError, match="unknown origin airport 'XYZ'"):
            loader.load_from_directory(temp_dir)

        # Restore
        flights_file.write_text(content, encoding="utf-8")

        # 2. Duplicate airport in airports.csv
        airports_file = temp_dir / "airports.csv"
        orig_airports = airports_file.read_text(encoding="utf-8")
        corrupted_airports = orig_airports + "\nBOM,Duplicate BOM,Mumbai,India,19800,19.0,72.0,true,,\n"
        airports_file.write_text(corrupted_airports, encoding="utf-8")

        with pytest.raises(DatasetValidationError, match="Duplicate airport code 'BOM'"):
            loader.load_from_directory(temp_dir)

        # Restore
        airports_file.write_text(orig_airports, encoding="utf-8")

        # 3. Inverted flight departure/arrival interval
        lines = content.splitlines()
        # Header is line 0. Line 1 is NV-101. Replace arrival with earlier timestamp than departure
        parts = lines[1].split(",")
        parts[4] = str(int(parts[3]) - 1000)  # arrival_utc < departure_utc
        corrupted_flight_lines = [lines[0], ",".join(parts)] + lines[2:]
        flights_file.write_text("\n".join(corrupted_flight_lines), encoding="utf-8")

        with pytest.raises(DatasetValidationError, match="Invalid flight interval"):
            loader.load_from_directory(temp_dir)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
