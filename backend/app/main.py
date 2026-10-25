"""FastAPI application entry point for Nova Air (AirCrewOps) Operations Control Center."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import api_router
from backend.app.rules.profile_loader import load_rule_profile
from backend.app.services.aircraft_service import AircraftService
from backend.app.services.constraint_engine import ConstraintEngine
from backend.app.services.crew_service import CrewService
from backend.app.services.disruption_service import DisruptionService
from backend.app.services.index_manager import ADSIndexManager
from backend.app.services.persistence_service import PersistenceService
from backend.app.services.positioning_service import PositioningService
from backend.app.services.roster_scheduler import RosterScheduler
from backend.app.websocket.manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize SQLite persistence and build in-memory ADS indexes."""
    app.state.start_time = time.time()
    db_path = getattr(app.state, "db_path", "data/aircrewops.db")
    persist = PersistenceService(db_path=db_path)

    # Check if DB needs initial seeding
    with persist.get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS cnt FROM flights;").fetchone()["cnt"]
        if count == 0:
            demo_dir = Path("data")
            if (demo_dir / "flights.csv").exists():
                persist.seed_from_csv(demo_dir, profile="demo")

    rule_profile = load_rule_profile()
    idx_mgr = ADSIndexManager(rule_profile=rule_profile)
    persist.rebuild_indexes_from_db(idx_mgr)

    pos_service = PositioningService(idx_mgr.connection_graph, rule_profile)
    ce = ConstraintEngine(rule_profile, pos_service)
    scheduler = RosterScheduler(idx_mgr, ce, pos_service, rule_profile)
    crew_svc = CrewService(idx_mgr, persist)
    ac_svc = AircraftService(idx_mgr, persist)
    disruption_svc = DisruptionService(idx_mgr, ce, pos_service, scheduler, persist, rule_profile)

    app.state.persistence_service = persist
    app.state.index_manager = idx_mgr
    app.state.positioning_service = pos_service
    app.state.constraint_engine = ce
    app.state.roster_scheduler = scheduler
    app.state.crew_service = crew_svc
    app.state.aircraft_service = ac_svc
    app.state.disruption_service = disruption_svc

    yield


app = FastAPI(
    title="Nova Air OCC - AirCrewOps",
    description="Real-Time Airline Crew Rostering & Aircraft Rotation Optimization Simulator backed by custom ADS.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes under /api/v1
app.include_router(api_router, prefix="/api/v1")


# WebSocket Endpoints
@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """Real-time operational event stream."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep-alive receive loop
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        ws_manager.disconnect(websocket)


@app.websocket("/ws/operations")
async def websocket_operations_endpoint(websocket: WebSocket):
    """Operations center telemetry stream."""
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        ws_manager.disconnect(websocket)


@app.get("/")
def get_root():
    """Root landing endpoint with system status and documentation links."""
    return {
        "name": "AirCrewOps API",
        "airline": "Nova Air",
        "active_rule_profile": "nova_air_demo_v1",
        "is_educational_simulator": True,
        "docs_url": "/docs",
        "api_v1_url": "/api/v1",
    }
