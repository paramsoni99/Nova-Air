"""PersistenceService: Transactional SQLite database coordinator for Nova Air.

Manages relational schema, CSV seeding, index rebuilding into ADS structures,
and atomic write transactions with rollback on constraint violations.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

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
    RosterAssignment,
    RosterStatus,
)
from backend.app.services.dataset_loader import DatasetLoader
from backend.app.services.index_manager import ADSIndexManager


class PersistenceService:
    """Transactional SQLite persistence service backed by data/aircrewops.db."""

    def __init__(self, db_path: str | Path = "data/aircrewops.db") -> None:
        self.db_path: Path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with foreign keys and row factory enabled."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic SQLite write transaction with rollback on failure."""
        conn = self.get_connection()
        try:
            conn.execute("BEGIN TRANSACTION;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create relational tables, indices, and constraints if they do not exist."""
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS airports (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
                    country TEXT NOT NULL,
                    timezone_offset_seconds INTEGER NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    is_hub INTEGER NOT NULL,
                    curfew_start_hour_utc INTEGER,
                    curfew_end_hour_utc INTEGER
                );

                CREATE TABLE IF NOT EXISTS aircraft (
                    tail_number TEXT PRIMARY KEY,
                    aircraft_type TEXT NOT NULL,
                    home_base TEXT NOT NULL,
                    seating_capacity INTEGER NOT NULL,
                    total_flight_hours REAL NOT NULL,
                    is_active INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS maintenance_windows (
                    id TEXT PRIMARY KEY,
                    aircraft_tail TEXT NOT NULL,
                    airport_code TEXT NOT NULL,
                    start_utc INTEGER NOT NULL,
                    end_utc INTEGER NOT NULL,
                    description TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS crew_members (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    home_base TEXT NOT NULL,
                    current_airport TEXT NOT NULL,
                    cumulative_flight_seconds_7d INTEGER NOT NULL,
                    cumulative_duty_seconds_7d INTEGER NOT NULL,
                    last_duty_end_utc INTEGER,
                    is_active INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS crew_qualifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    crew_id TEXT NOT NULL,
                    aircraft_type TEXT NOT NULL,
                    valid_until_utc INTEGER NOT NULL,
                    FOREIGN KEY(crew_id) REFERENCES crew_members(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS flights (
                    flight_number TEXT PRIMARY KEY,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    departure_utc INTEGER NOT NULL,
                    arrival_utc INTEGER NOT NULL,
                    aircraft_tail TEXT,
                    required_aircraft_type TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS duty_periods (
                    id TEXT PRIMARY KEY,
                    crew_id TEXT NOT NULL,
                    flight_leg_ids TEXT NOT NULL,
                    report_utc INTEGER NOT NULL,
                    release_utc INTEGER NOT NULL,
                    duty_type TEXT NOT NULL,
                    total_flight_seconds INTEGER NOT NULL,
                    FOREIGN KEY(crew_id) REFERENCES crew_members(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS roster_assignments (
                    id TEXT PRIMARY KEY,
                    flight_number TEXT UNIQUE NOT NULL,
                    captain_id TEXT,
                    first_officer_id TEXT,
                    cabin_crew_ids TEXT,
                    aircraft_tail TEXT,
                    status TEXT NOT NULL,
                    FOREIGN KEY(flight_number) REFERENCES flights(flight_number) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_flights_departure ON flights(departure_utc);
                CREATE INDEX IF NOT EXISTS idx_crew_role ON crew_members(role);
                CREATE INDEX IF NOT EXISTS idx_maint_aircraft ON maintenance_windows(aircraft_tail);
            """)

    def seed_from_csv(
        self,
        dataset_dir: Path | str,
        profile: str = "demo",
        clear_existing: bool = True,
    ) -> None:
        """Seed SQLite database deterministically from CSV directory files."""
        loader = DatasetLoader()
        dataset = loader.load_from_directory(dataset_dir)

        with self.transaction() as conn:
            if clear_existing:
                conn.execute("DELETE FROM roster_assignments;")
                conn.execute("DELETE FROM duty_periods;")
                conn.execute("DELETE FROM crew_qualifications;")
                conn.execute("DELETE FROM crew_members;")
                conn.execute("DELETE FROM maintenance_windows;")
                conn.execute("DELETE FROM flights;")
                conn.execute("DELETE FROM aircraft;")
                conn.execute("DELETE FROM airports;")

            # 1. Airports
            for ap in dataset.airports.values():
                conn.execute(
                    """
                    INSERT INTO airports (code, name, city, country, timezone_offset_seconds, latitude, longitude, is_hub, curfew_start_hour_utc, curfew_end_hour_utc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ap.code, ap.name, ap.city, ap.country, ap.timezone_offset_seconds,
                        ap.latitude, ap.longitude, 1 if ap.is_hub else 0,
                        ap.curfew_start_hour_utc, ap.curfew_end_hour_utc,
                    ),
                )

            # 2. Aircraft
            for ac in dataset.aircraft.values():
                conn.execute(
                    """
                    INSERT INTO aircraft (tail_number, aircraft_type, home_base, seating_capacity, total_flight_hours, is_active)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ac.tail_number, ac.aircraft_type, ac.home_base,
                        ac.seating_capacity, ac.total_flight_hours, 1 if ac.is_active else 0,
                    ),
                )

            # 3. Maintenance
            for mw in dataset.maintenance:
                conn.execute(
                    """
                    INSERT INTO maintenance_windows (id, aircraft_tail, airport_code, start_utc, end_utc, description)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (mw.id, mw.aircraft_tail, mw.airport_code, mw.start_utc, mw.end_utc, mw.description),
                )

            # 4. Crew & Qualifications
            for c in dataset.crew.values():
                conn.execute(
                    """
                    INSERT INTO crew_members (id, name, role, home_base, current_airport, cumulative_flight_seconds_7d, cumulative_duty_seconds_7d, last_duty_end_utc, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        c.id, c.name, c.role.value, c.home_base, c.current_airport,
                        c.cumulative_flight_seconds_7d, c.cumulative_duty_seconds_7d,
                        c.last_duty_end_utc, 1 if c.is_active else 0,
                    ),
                )
                for q in c.qualifications:
                    conn.execute(
                        """
                        INSERT INTO crew_qualifications (crew_id, aircraft_type, valid_until_utc)
                        VALUES (?, ?, ?);
                        """,
                        (c.id, q.aircraft_type, q.valid_until_utc),
                    )

            # 5. Flights
            for fl in dataset.flights:
                conn.execute(
                    """
                    INSERT INTO flights (flight_number, origin, destination, departure_utc, arrival_utc, aircraft_tail, required_aircraft_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        fl.flight_number, fl.origin, fl.destination,
                        fl.departure_utc, fl.arrival_utc, fl.aircraft_tail,
                        fl.required_aircraft_type,
                    ),
                )

            # 6. Duty History
            for dh in dataset.duty_history:
                conn.execute(
                    """
                    INSERT INTO duty_periods (id, crew_id, flight_leg_ids, report_utc, release_utc, duty_type, total_flight_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        dh.id, dh.crew_id, ";".join(dh.flight_leg_ids),
                        dh.report_utc, dh.release_utc, dh.duty_type.value,
                        dh.total_flight_seconds,
                    ),
                )

    def rebuild_indexes_from_db(self, index_manager: ADSIndexManager) -> None:
        """Reconstruct in-memory ADS data structures deterministically from SQLite state."""
        with self.get_connection() as conn:
            # Airports
            airports: List[Airport] = []
            for r in conn.execute("SELECT * FROM airports;"):
                airports.append(
                    Airport(
                        code=r["code"],
                        name=r["name"],
                        city=r["city"],
                        country=r["country"],
                        timezone_offset_seconds=r["timezone_offset_seconds"],
                        latitude=r["latitude"],
                        longitude=r["longitude"],
                        is_hub=bool(r["is_hub"]),
                        curfew_start_hour_utc=r["curfew_start_hour_utc"],
                        curfew_end_hour_utc=r["curfew_end_hour_utc"],
                    )
                )

            # Aircraft
            aircraft: List[Aircraft] = []
            for r in conn.execute("SELECT * FROM aircraft;"):
                aircraft.append(
                    Aircraft(
                        tail_number=r["tail_number"],
                        aircraft_type=r["aircraft_type"],
                        home_base=r["home_base"],
                        seating_capacity=r["seating_capacity"],
                        total_flight_hours=r["total_flight_hours"],
                        is_active=bool(r["is_active"]),
                    )
                )

            # Maintenance
            maintenance: List[MaintenanceWindow] = []
            for r in conn.execute("SELECT * FROM maintenance_windows;"):
                maintenance.append(
                    MaintenanceWindow(
                        id=r["id"],
                        aircraft_tail=r["aircraft_tail"],
                        airport_code=r["airport_code"],
                        start_utc=r["start_utc"],
                        end_utc=r["end_utc"],
                        description=r["description"],
                    )
                )

            # Qualifications
            quals_by_crew: Dict[str, List[CrewQualification]] = {}
            for r in conn.execute("SELECT * FROM crew_qualifications;"):
                quals_by_crew.setdefault(r["crew_id"], []).append(
                    CrewQualification(
                        aircraft_type=r["aircraft_type"],
                        valid_until_utc=r["valid_until_utc"],
                    )
                )

            # Crew
            crew: List[CrewMember] = []
            for r in conn.execute("SELECT * FROM crew_members;"):
                cid = r["id"]
                crew.append(
                    CrewMember(
                        id=cid,
                        name=r["name"],
                        role=CrewRole(r["role"]),
                        home_base=r["home_base"],
                        current_airport=r["current_airport"],
                        qualifications=quals_by_crew.get(cid, []),
                        cumulative_flight_seconds_7d=r["cumulative_flight_seconds_7d"],
                        cumulative_duty_seconds_7d=r["cumulative_duty_seconds_7d"],
                        last_duty_end_utc=r["last_duty_end_utc"],
                        is_active=bool(r["is_active"]),
                    )
                )

            # Flights
            flights: List[FlightLeg] = []
            for r in conn.execute("SELECT * FROM flights;"):
                flights.append(
                    FlightLeg(
                        flight_number=r["flight_number"],
                        origin=r["origin"],
                        destination=r["destination"],
                        departure_utc=r["departure_utc"],
                        arrival_utc=r["arrival_utc"],
                        aircraft_tail=r["aircraft_tail"],
                        required_aircraft_type=r["required_aircraft_type"],
                    )
                )

            # Duty Periods
            duty_history: List[DutyPeriod] = []
            for r in conn.execute("SELECT * FROM duty_periods;"):
                legs = [x.strip() for x in r["flight_leg_ids"].split(";") if x.strip()]
                duty_history.append(
                    DutyPeriod(
                        id=r["id"],
                        crew_id=r["crew_id"],
                        flight_leg_ids=legs,
                        report_utc=r["report_utc"],
                        release_utc=r["release_utc"],
                        duty_type=DutyType(r["duty_type"]),
                        total_flight_seconds=r["total_flight_seconds"],
                    )
                )

        # Build in-memory ADS state
        index_manager.build_from_domain_state(
            airports=airports,
            aircraft=aircraft,
            maintenance=maintenance,
            crew=crew,
            flights=flights,
            duty_history=duty_history,
        )

    def save_flight(self, flight: FlightLeg) -> None:
        """Insert or replace flight in SQLite database."""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO flights (flight_number, origin, destination, departure_utc, arrival_utc, aircraft_tail, required_aircraft_type)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    flight.flight_number, flight.origin, flight.destination,
                    flight.departure_utc, flight.arrival_utc, flight.aircraft_tail,
                    flight.required_aircraft_type,
                ),
            )

    def save_assignment(self, assignment: RosterAssignment) -> None:
        """Insert or update roster assignment in SQLite database."""
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO roster_assignments (id, flight_number, captain_id, first_officer_id, cabin_crew_ids, aircraft_tail, status)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    assignment.id,
                    assignment.flight_number,
                    assignment.captain_id,
                    assignment.first_officer_id,
                    json.dumps(assignment.cabin_crew_ids),
                    assignment.aircraft_tail,
                    assignment.status.value,
                ),
            )

    def save_crew(self, crew: CrewMember) -> None:
        """Update crew member attributes in SQLite database."""
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE crew_members
                SET current_airport = ?, cumulative_flight_seconds_7d = ?, cumulative_duty_seconds_7d = ?, last_duty_end_utc = ?, is_active = ?
                WHERE id = ?;
                """,
                (
                    crew.current_airport,
                    crew.cumulative_flight_seconds_7d,
                    crew.cumulative_duty_seconds_7d,
                    crew.last_duty_end_utc,
                    1 if crew.is_active else 0,
                    crew.id,
                ),
            )

    def get_flight(self, flight_number: str) -> Optional[FlightLeg]:
        """Fetch single flight from SQLite."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM flights WHERE flight_number = ?;", (flight_number,)).fetchone()
            if row is None:
                return None
            return FlightLeg(
                flight_number=row["flight_number"],
                origin=row["origin"],
                destination=row["destination"],
                departure_utc=row["departure_utc"],
                arrival_utc=row["arrival_utc"],
                aircraft_tail=row["aircraft_tail"],
                required_aircraft_type=row["required_aircraft_type"],
            )

    def get_assignment(self, flight_number: str) -> Optional[RosterAssignment]:
        """Fetch assignment by flight number from SQLite."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM roster_assignments WHERE flight_number = ?;", (flight_number,)).fetchone()
            if row is None:
                return None
            cabin_crew = json.loads(row["cabin_crew_ids"]) if row["cabin_crew_ids"] else []
            return RosterAssignment(
                id=row["id"],
                flight_number=row["flight_number"],
                captain_id=row["captain_id"],
                first_officer_id=row["first_officer_id"],
                cabin_crew_ids=cabin_crew,
                aircraft_tail=row["aircraft_tail"],
                status=RosterStatus(row["status"]),
            )

    def export_to_csv(self, output_dir: Path | str) -> None:
        """Export current SQLite state to directory of CSV files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        with self.get_connection() as conn:
            # Flights
            with open(out / "flights.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["flight_number", "origin", "destination", "departure_utc", "arrival_utc", "aircraft_tail", "required_aircraft_type"])
                for r in conn.execute("SELECT * FROM flights ORDER BY departure_utc;"):
                    writer.writerow([r["flight_number"], r["origin"], r["destination"], r["departure_utc"], r["arrival_utc"], r["aircraft_tail"] or "", r["required_aircraft_type"]])
