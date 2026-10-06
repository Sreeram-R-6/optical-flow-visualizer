import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from .mavlink_connection import MAVLinkConnection
from .models import ConnectRequest, Settings, SimulationInput
from .serial_ports import available_ports
from .telemetry import TelemetryState
from .websocket_manager import WebSocketManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
state = TelemetryState()
connection = MAVLinkConnection(state)
manager = WebSocketManager(state)
ALLOWED_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(manager.broadcast())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await manager.close()
    await asyncio.to_thread(connection.disconnect)

app = FastAPI(title="Optical Flow Visualizer", lifespan=lifespan)

@app.middleware("http")
async def local_only(request: Request, call_next):
    # Protect localhost serial actions from cross-origin browser requests.
    from starlette.responses import JSONResponse
    if request.headers.get("host", "").split(":")[0] not in {"127.0.0.1", "localhost", "testserver"}:
        return JSONResponse({"detail": "Localhost only"}, status_code=403)
    if request.headers.get("origin") and request.headers["origin"] not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)

@app.get("/api/health")
def health():
    return {"ok": True, "read_only": True}

@app.get("/api/ports")
def ports():
    try:
        return available_ports()
    except Exception as exc:
        raise HTTPException(503, f"Serial discovery failed: {exc}") from exc

@app.get("/api/status")
def status():
    return state.snapshot()

@app.post("/api/connect")
def connect(body: ConnectRequest):
    if body.port.upper() not in {p["device"].upper() for p in available_ports()}:
        raise HTTPException(400, "COM port unavailable. Refresh the port list.")
    try:
        connection.connect(body.port.upper(), body.baud)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return state.snapshot()

@app.post("/api/disconnect")
def disconnect():
    try:
        connection.disconnect()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return state.snapshot()

@app.post("/api/reset-origin")
def reset_origin():
    state.reset_origin()
    return state.snapshot()

@app.post("/api/settings")
def settings(body: Settings):
    state.update_settings(body)
    return state.settings.model_dump()

@app.post("/api/simulation/start")
def simulation():
    try:
        connection.connect(None, simulation=True)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return state.snapshot()

@app.post("/api/simulation/input")
def simulation_input(body: SimulationInput):
    try:
        connection.set_sim_input(body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}

@app.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket):
    if ws.headers.get("origin") not in ALLOWED_ORIGINS | {None}:
        await ws.close(code=1008)
        return
    await ws.accept()
    manager.clients.add(ws)
    try:
        await ws.send_json(state.snapshot())
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        manager.clients.discard(ws)

dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
