"""Dataset loader and integrity validator for Nova Air.

Loads CSV datasets into validated domain models and cross-references foreign keys,
timestamps, and geographical integrity against the active rule profile.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

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
    RuleProfile,
)
from backend.app.rules.profile_loader import load_rule_profile


class DatasetValidationError(Exception):
    """Raised when dataset rows fail foreign key, interval, or domain integrity checks."""
    pass


@dataclass
class AirlineDataset:
    airports: Dict[str, Airport]
    aircraft: Dict[str, Aircraft]
    maintenance: List[MaintenanceWindow]
    crew: Dict[str, CrewMember]
    flights: List[FlightLeg]
    duty_history: List[DutyPeriod]

    def get_airport(self, code: str) -> Optional[Airport]:
        return self.airports.get(code.upper())

    def get_aircraft(self, tail: str) -> Optional[Aircraft]:
        return self.aircraft.get(tail.upper())

    def get_crew(self, crew_id: str) -> Optional[CrewMember]:
        return self.crew.get(crew_id.upper())

    def get_flight(self, flight_number: str) -> Optional[FlightLeg]:
        for f in self.flights:
            if f.flight_number == flight_number.upper():
                return f
        return None


class DatasetLoader:
    def __init__(self, rule_profile: Optional[RuleProfile] = None):
        self.profile = rule_profile or load_rule_profile("nova_air_demo_v1")

    def load_from_directory(self, dataset_dir: Path | str) -> AirlineDataset:
        dir_path = Path(dataset_dir)
        if not dir_path.is_dir():
            raise FileNotFoundError(f"Dataset directory not found: {dir_path}")

        airports = self._load_airports(dir_path / "airports.csv")
        aircraft = self._load_aircraft(dir_path / "aircraft.csv", set(airports.keys()))
        maintenance = self._load_maintenance(
            dir_path / "maintenance.csv", set(aircraft.keys()), set(airports.keys())
        )
        crew = self._load_crew(
            dir_path / "crew.csv",
            dir_path / "qualifications.csv",
            set(airports.keys()),
        )
        flights = self._load_flights(
            dir_path / "flights.csv", set(airports.keys()), set(aircraft.keys())
        )
        duty_history = self._load_duty_history(
            dir_path / "duty_history.csv", set(crew.keys())
        )

        return AirlineDataset(
            airports=airports,
            aircraft=aircraft,
            maintenance=maintenance,
            crew=crew,
            flights=flights,
            duty_history=duty_history,
        )

    def _load_airports(self, filepath: Path) -> Dict[str, Airport]:
        if not filepath.exists():
            raise FileNotFoundError(f"Missing required file: {filepath}")

        airports: Dict[str, Airport] = {}
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                code = row["code"].strip().upper()
                if code in airports:
                    raise DatasetValidationError(f"Duplicate airport code '{code}' at row {row_idx}")
                try:
                    curfew_start = int(row["curfew_start_hour_utc"]) if row.get("curfew_start_hour_utc") else None
                    curfew_end = int(row["curfew_end_hour_utc"]) if row.get("curfew_end_hour_utc") else None
                    is_hub = str(row.get("is_hub", "")).strip().lower() in {"true", "1", "yes"}

                    airport = Airport(
                        code=code,
                        name=row["name"].strip(),
                        city=row["city"].strip(),
                        country=row.get("country", "India").strip(),
                        timezone_offset_seconds=int(row.get("timezone_offset_seconds", 19800)),
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        is_hub=is_hub,
                        curfew_start_hour_utc=curfew_start,
                        curfew_end_hour_utc=curfew_end,
                    )
                    airports[code] = airport
                except Exception as e:
                    raise DatasetValidationError(f"Invalid airport data at row {row_idx} ({code}): {e}") from e

        return airports

    def _load_aircraft(self, filepath: Path, airport_codes: Set[str]) -> Dict[str, Aircraft]:
        if not filepath.exists():
            raise FileNotFoundError(f"Missing required file: {filepath}")

        aircraft_dict: Dict[str, Aircraft] = {}
        valid_types = set(self.profile.aircraft_turnaround_times_seconds.keys())

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                tail = row["tail_number"].strip().upper()
                atype = row["aircraft_type"].strip().upper()
                home_base = row["home_base"].strip().upper()

                if tail in aircraft_dict:
                    raise DatasetValidationError(f"Duplicate aircraft tail '{tail}' at row {row_idx}")
                if home_base not in airport_codes:
                    raise DatasetValidationError(f"Aircraft '{tail}' has unknown home_base '{home_base}' at row {row_idx}")
                if atype not in valid_types:
                    raise DatasetValidationError(f"Aircraft '{tail}' has unsupported type '{atype}' (allowed: {valid_types}) at row {row_idx}")

                try:
                    is_active = str(row.get("is_active", "")).strip().lower() in {"true", "1", "yes"}
                    ac = Aircraft(
                        tail_number=tail,
                        aircraft_type=atype,
                        home_base=home_base,
                        seating_capacity=int(row["seating_capacity"]),
                        total_flight_hours=float(row.get("total_flight_hours", 0.0)),
                        is_active=is_active,
                    )
                    aircraft_dict[tail] = ac
                except Exception as e:
                    raise DatasetValidationError(f"Invalid aircraft data at row {row_idx} ({tail}): {e}") from e

        return aircraft_dict

    def _load_maintenance(
        self, filepath: Path, aircraft_tails: Set[str], airport_codes: Set[str]
    ) -> List[MaintenanceWindow]:
        if not filepath.exists():
            return []

        windows: List[MaintenanceWindow] = []
        seen_ids: Set[str] = set()

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                mid = row["id"].strip().upper()
                tail = row["aircraft_tail"].strip().upper()
                airport = row["airport_code"].strip().upper()

                if mid in seen_ids:
                    raise DatasetValidationError(f"Duplicate maintenance id '{mid}' at row {row_idx}")
                if tail not in aircraft_tails:
                    raise DatasetValidationError(f"Maintenance window '{mid}' references unknown aircraft '{tail}' at row {row_idx}")
                if airport not in airport_codes:
                    raise DatasetValidationError(f"Maintenance window '{mid}' references unknown airport '{airport}' at row {row_idx}")

                try:
                    w = MaintenanceWindow(
                        id=mid,
                        aircraft_tail=tail,
                        airport_code=airport,
                        start_utc=int(row["start_utc"]),
                        end_utc=int(row["end_utc"]),
                        description=row.get("description", "Scheduled check").strip(),
                    )
                    windows.append(w)
                    seen_ids.add(mid)
                except Exception as e:
                    raise DatasetValidationError(f"Invalid maintenance interval at row {row_idx} ({mid}): {e}") from e

        return windows

    def _load_crew(
        self, crew_filepath: Path, qual_filepath: Path, airport_codes: Set[str]
    ) -> Dict[str, CrewMember]:
        if not crew_filepath.exists():
            raise FileNotFoundError(f"Missing required file: {crew_filepath}")

        # Load qualifications first
        quals_by_crew: Dict[str, List[CrewQualification]] = {}
        if qual_filepath.exists():
            with open(qual_filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    cid = row["crew_id"].strip().upper()
                    atype = row["aircraft_type"].strip().upper()
                    try:
                        q = CrewQualification(
                            aircraft_type=atype,
                            valid_until_utc=int(row["valid_until_utc"]),
                        )
                        quals_by_crew.setdefault(cid, []).append(q)
                    except Exception as e:
                        raise DatasetValidationError(f"Invalid qualification at row {row_idx} ({cid}): {e}") from e

        crew_dict: Dict[str, CrewMember] = {}
        with open(crew_filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                cid = row["id"].strip().upper()
                role_str = row["role"].strip().upper()
                base = row["home_base"].strip().upper()
                curr = row.get("current_airport", base).strip().upper()

                if cid in crew_dict:
                    raise DatasetValidationError(f"Duplicate crew ID '{cid}' at row {row_idx}")
                if base not in airport_codes:
                    raise DatasetValidationError(f"Crew '{cid}' has unknown home_base '{base}' at row {row_idx}")
                if curr not in airport_codes:
                    raise DatasetValidationError(f"Crew '{cid}' has unknown current_airport '{curr}' at row {row_idx}")

                try:
                    role = CrewRole(role_str)
                except ValueError:
                    raise DatasetValidationError(f"Crew '{cid}' has invalid role '{role_str}' at row {row_idx}")

                try:
                    last_duty = int(row["last_duty_end_utc"]) if row.get("last_duty_end_utc") else None
                    is_active = str(row.get("is_active", "")).strip().lower() in {"true", "1", "yes"}

                    member = CrewMember(
                        id=cid,
                        name=row["name"].strip(),
                        role=role,
                        home_base=base,
                        current_airport=curr,
                        qualifications=quals_by_crew.get(cid, []),
                        cumulative_flight_seconds_7d=int(row.get("cumulative_flight_seconds_7d", 0)),
                        cumulative_duty_seconds_7d=int(row.get("cumulative_duty_seconds_7d", 0)),
                        last_duty_end_utc=last_duty,
                        is_active=is_active,
                    )
                    crew_dict[cid] = member
                except Exception as e:
                    raise DatasetValidationError(f"Invalid crew data at row {row_idx} ({cid}): {e}") from e

        return crew_dict

    def _load_flights(
        self, filepath: Path, airport_codes: Set[str], aircraft_tails: Set[str]
    ) -> List[FlightLeg]:
        if not filepath.exists():
            raise FileNotFoundError(f"Missing required file: {filepath}")

        flights: List[FlightLeg] = []
        seen_numbers: Set[str] = set()

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                fn = row["flight_number"].strip().upper()
                orig = row["origin"].strip().upper()
                dest = row["destination"].strip().upper()
                tail = row.get("aircraft_tail", "").strip().upper() or None
                req_type = row.get("required_aircraft_type", "A320").strip().upper()

                if fn in seen_numbers:
                    raise DatasetValidationError(f"Duplicate flight number '{fn}' at row {row_idx}")
                if orig not in airport_codes:
                    raise DatasetValidationError(f"Flight '{fn}' has unknown origin airport '{orig}' at row {row_idx}")
                if dest not in airport_codes:
                    raise DatasetValidationError(f"Flight '{fn}' has unknown destination airport '{dest}' at row {row_idx}")
                if orig == dest:
                    raise DatasetValidationError(f"Flight '{fn}' origin and destination cannot be identical ({orig}) at row {row_idx}")
                if tail and tail not in aircraft_tails:
                    raise DatasetValidationError(f"Flight '{fn}' assigned unknown aircraft '{tail}' at row {row_idx}")

                try:
                    leg = FlightLeg(
                        flight_number=fn,
                        origin=orig,
                        destination=dest,
                        departure_utc=int(row["departure_utc"]),
                        arrival_utc=int(row["arrival_utc"]),
                        aircraft_tail=tail,
                        required_aircraft_type=req_type,
                    )
                    flights.append(leg)
                    seen_numbers.add(fn)
                except Exception as e:
                    raise DatasetValidationError(f"Invalid flight interval or parameters at row {row_idx} ({fn}): {e}") from e

        return flights

    def _load_duty_history(self, filepath: Path, crew_ids: Set[str]) -> List[DutyPeriod]:
        if not filepath.exists():
            return []

        history: List[DutyPeriod] = []
        seen_ids: Set[str] = set()

        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):
                did = row["id"].strip().upper()
                cid = row["crew_id"].strip().upper()

                if did in seen_ids:
                    raise DatasetValidationError(f"Duplicate duty period ID '{did}' at row {row_idx}")
                if cid not in crew_ids:
                    raise DatasetValidationError(f"Duty history '{did}' references unknown crew '{cid}' at row {row_idx}")

                legs_raw = row.get("flight_leg_ids", "").strip()
                leg_ids = [item.strip() for item in legs_raw.split(";") if item.strip()] if legs_raw else []

                try:
                    duty_type_str = row.get("duty_type", "FLIGHT_DUTY").strip().upper()
                    duty_type = DutyType(duty_type_str)
                except ValueError:
                    duty_type = DutyType.FLIGHT_DUTY

                try:
                    period = DutyPeriod(
                        id=did,
                        crew_id=cid,
                        flight_leg_ids=leg_ids,
                        report_utc=int(row["report_utc"]),
                        release_utc=int(row["release_utc"]),
                        duty_type=duty_type,
                        total_flight_seconds=int(row.get("total_flight_seconds", 0)),
                    )
                    history.append(period)
                    seen_ids.add(did)
                except Exception as e:
                    raise DatasetValidationError(f"Invalid duty period interval at row {row_idx} ({did}): {e}") from e

        return history
