"""Stateless hosted demo. No serial imports, background workers or shared sessions."""
import math
from fastapi import FastAPI, Response
from pydantic import BaseModel, ConfigDict, Field
from backend.models import Settings, SimulationInput
from backend.flow_processor import simulated_packets
from backend.telemetry import TelemetryState

app = FastAPI(title="Optical Flow Hosted Demo")


class DemoSession(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    settings: Settings = Field(default_factory=Settings)
    controls: SimulationInput = Field(default_factory=SimulationInput)
    active: bool = False
    revision: int = Field(default=0, ge=0, le=1_000_000_000)
    elapsed: float = Field(default=0, ge=0, le=1_000_000_000)
    north: float = Field(default=0, ge=-1e9, le=1e9)
    east: float = Field(default=0, ge=-1e9, le=1e9)
    flow_north: float = Field(default=0, ge=-1e9, le=1e9)
    flow_east: float = Field(default=0, ge=-1e9, le=1e9)


class DemoStep(BaseModel):
    session: DemoSession = Field(default_factory=DemoSession)
    dt: float = Field(default=0.2, ge=0, le=0.5, allow_inf_nan=False)


@app.get("/api/health")
def health():
    return {"ok": True, "read_only": True, "mode": "hosted_demo"}


@app.get("/api/ports")
def ports():
    return []


@app.post("/api/demo/step")
def step(body: DemoStep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    session = body.session.model_copy(deep=True)
    state = TelemetryState()
    state.events.clear()
    state.settings = session.settings
    state.revision = session.revision
    if session.active:
        state.simulation = True
        state.processor.north, state.processor.east = session.flow_north, session.flow_east
        state.origin = (0, 0)
        # Prime the legacy rate baseline, then process bounded 50 ms samples.
        state.processor.rate_time = session.elapsed
        count = max(1, math.ceil(body.dt / 0.05))
        dt = body.dt / count
        for _ in range(count):
            session.elapsed += dt
            t = session.elapsed
            if session.controls.mode == "auto":
                vn, ve = 0.6 * math.cos(t * 0.45), 0.6 * math.sin(t * 0.45)
            else:
                vn, ve = session.controls.north * 0.8, session.controls.east * 0.8
            session.north += vn * dt
            session.east += ve * dt
            for kind, raw in simulated_packets(t, dt, session.north, session.east, vn, ve):
                state.ingest(kind, raw, t)
        session.flow_north, session.flow_east = state.processor.north, state.processor.east
    snapshot = state.snapshot(now=session.elapsed)
    snapshot["mode"] = "hosted_demo"
    return {"session": session.model_dump(), "telemetry": snapshot}
