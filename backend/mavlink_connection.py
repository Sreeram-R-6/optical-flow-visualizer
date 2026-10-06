import math
import threading
import time
from pymavlink import mavutil
from .config import CONNECT_TIMEOUT, HEARTBEAT_TIMEOUT, MESSAGE_RATES
from .models import SimulationInput
from .telemetry import TelemetryState

class MAVLinkConnection:
    """Single serial owner. Reader never runs on the asyncio event loop."""
    def __init__(self, state: TelemetryState) -> None:
        self.state = state
        self.worker: threading.Thread | None = None
        self.stop = threading.Event()
        self.lifecycle_lock = threading.Lock()
        self.sim_input = SimulationInput()
        self.sim_input_time = time.monotonic()

    def disconnect(self) -> None:
        with self.lifecycle_lock:
            self._stop()
            with self.state.lock:
                self.state.simulation = False
                self.state.transition("DISCONNECTED")

    def _stop(self) -> None:
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=4)
            if self.worker.is_alive():
                raise RuntimeError("Serial reader is still closing; retry shortly")
        self.worker = None

    def connect(self, port: str | None, baud: int = 115200, simulation: bool = False) -> None:
        with self.lifecycle_lock:
            self._stop()
            self.stop = threading.Event()
            with self.state.lock:
                self.state.clear_data()
                self.state.simulation = simulation
                self.state.port = None if simulation else port
                self.state.baud = baud
                self.state.transition("CONNECTING")
            self.sim_input = SimulationInput()
            self.worker = threading.Thread(target=self._simulate if simulation else self._read,
                                           args=() if simulation else (port, baud), daemon=True, name="telemetry-reader")
            self.worker.start()

    def set_sim_input(self, controls: SimulationInput) -> None:
        with self.state.lock:
            if not self.state.simulation:
                raise ValueError("Manual input is available only in simulation")
            self.sim_input = controls
            self.sim_input_time = time.monotonic()

    def _request_intervals(self, link, system: int, component: int) -> None:
        for name, hz in MESSAGE_RATES.items():
            try:
                message_id = getattr(mavutil.mavlink, f"MAVLINK_MSG_ID_{name}", None)
                if message_id is not None:
                    # The ONLY outbound MAVLink command in this application.
                    link.mav.command_long_send(system, component, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                                               0, message_id, 1_000_000 / hz, 0, 0, 0, 0, 0)
            except Exception as exc:
                self.state.event(f"Could not request {name}: {exc}", "WARNING")

    def _read(self, port: str, baud: int) -> None:
        link = None
        try:
            link = mavutil.mavlink_connection(port, baud=baud, autoreconnect=False, robust_parsing=True,
                                             dialect="ardupilotmega")
            self.state.event(f"{port} opened at {baud} baud")
            self.state.transition("WAITING_FOR_HEARTBEAT")
            started = time.monotonic()
            target: tuple[int, int] | None = None
            while not self.stop.is_set():
                now = time.monotonic()
                msg = link.recv_match(blocking=False)
                if msg:
                    kind = msg.get_type()
                    if kind == "BAD_DATA":
                        with self.state.lock:
                            self.state.invalid_packets += 1
                        continue
                    if kind == "HEARTBEAT" and target is None:
                        if msg.autopilot == mavutil.mavlink.MAV_AUTOPILOT_INVALID or msg.type == mavutil.mavlink.MAV_TYPE_GCS:
                            continue
                        target = (msg.get_srcSystem(), msg.get_srcComponent())
                        self.state.system_id = target[0]
                        self.state.event(f"MAVLink heartbeat received; vehicle system ID {target[0]}")
                        self._request_intervals(link, *target)
                    if target and msg.get_srcSystem() == target[0]:
                        if kind != "HEARTBEAT" or msg.get_srcComponent() == target[1]:
                            self.state.ingest(kind, msg.to_dict(), now)
                        if kind == "COMMAND_ACK" and msg.command == mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL and msg.result != 0:
                            self.state.event(f"Message interval request result {msg.result}; listening to existing streams", "WARNING")
                else:
                    self.stop.wait(0.005)
                with self.state.lock:
                    hb = self.state.times.get("HEARTBEAT")
                if target is None and now - started > CONNECT_TIMEOUT:
                    raise TimeoutError("No vehicle HEARTBEAT in 12 seconds. Check port, baud and MAVLink configuration.")
                if hb is not None and now - hb > HEARTBEAT_TIMEOUT:
                    self.state.transition("CONNECTION_LOST", "MAVLink lost: heartbeat timeout. Reconnect to retry.")
                    break
        except Exception as exc:
            if not self.stop.is_set():
                state = "CONNECTION_LOST" if self.state.system_id else "ERROR"
                self.state.transition(state, f"Serial/MAVLink error: {exc}")
        finally:
            if link:
                try:
                    link.close()
                except Exception as exc:
                    self.state.event(f"Serial close: {exc}", "WARNING")

    def _simulate(self) -> None:
        self.state.event("SIMULATION started; no serial port or vehicle commands")
        n = e = 0.0
        last = start = time.monotonic()
        hb = 0.0
        while not self.stop.wait(0.05):
            now = time.monotonic()
            dt, last = min(now - last, 0.15), now
            t = now - start
            with self.state.lock:
                controls = self.sim_input
                expired = now - self.sim_input_time > 0.5
            if controls.mode == "auto":
                vn, ve = 0.6 * math.cos(t * 0.45), 0.6 * math.sin(t * 0.45)
            else:
                vn, ve = (0, 0) if expired else (controls.north * 0.8, controls.east * 0.8)
            n, e = n + vn * dt, e + ve * dt
            yaw = math.atan2(ve, vn) if vn or ve else 0.0
            d = 1.5 + 0.08 * math.sin(t)
            f = vn * math.cos(yaw) + ve * math.sin(yaw)
            r = -vn * math.sin(yaw) + ve * math.cos(yaw)
            if now - hb >= 1:
                self.state.ingest("HEARTBEAT", {"autopilot": 3, "type": 2}, now)
                hb = now
            self.state.ingest("ATTITUDE", {"roll": 0.02 * math.sin(t), "pitch": 0.015 * math.cos(t), "yaw": yaw}, now)
            self.state.ingest("DISTANCE_SENSOR", {"current_distance": round(d * 100), "min_distance": 10, "max_distance": 1000, "orientation": 25}, now)
            self.state.ingest("LOCAL_POSITION_NED", {"x": n, "y": e, "z": -d, "vx": vn, "vy": ve}, now)
            self.state.ingest("OPTICAL_FLOW_RAD", {"time_usec": int(t * 1e6), "sensor_id": 0,
                "integration_time_us": round(dt * 1e6), "integrated_x": -r * dt / d, "integrated_y": f * dt / d,
                "integrated_xgyro": 0.0, "integrated_ygyro": 0.0, "integrated_zgyro": 0.0,
                "temperature": 2400, "quality": int(225 + 18 * math.sin(t)), "time_delta_distance_us": 0, "distance": d}, now)
            self.state.ingest("OPTICAL_FLOW", {"time_usec": int(t * 1000), "sensor_id": 0,
                "flow_comp_m_x": -r / d, "flow_comp_m_y": f / d,
                "flow_x": 0, "flow_y": 0, "quality": int(225 + 18 * math.sin(t)),
                "ground_distance": d}, now)
