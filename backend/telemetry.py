import copy
import logging
import math
import threading
import time
from collections import deque
from .config import DATA_TIMEOUT, HEARTBEAT_TIMEOUT
from .flow_processor import FlowProcessor, finite, ned_position
from .models import Settings

logger = logging.getLogger(__name__)
MESSAGE_TYPES = ["HEARTBEAT", "OPTICAL_FLOW_RAD", "OPTICAL_FLOW", "DISTANCE_SENSOR", "LOCAL_POSITION_NED", "ATTITUDE", "SYS_STATUS"]

def age(last: float | None, now: float) -> float | None:
    return None if last is None else max(0, now - last)

def data_status(last: float | None, now: float, valid: bool = True) -> str:
    if last is None:
        return "NO DATA"
    if now - last > DATA_TIMEOUT:
        return "STALE"
    return "ACTIVE" if valid else "INVALID"

def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value

class TelemetryState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.settings = Settings()
        self.events: deque = deque(maxlen=100)
        self.revision = 0
        self.state = "DISCONNECTED"
        self.port: str | None = None
        self.baud = 115200
        self.error: str | None = None
        self.simulation = False
        self.clear_data()
        self.event("Backend started")

    def clear_data(self) -> None:
        self.raw: dict[str, dict] = {}
        self.times: dict[str, float] = {}
        self.rates = {t: deque(maxlen=100) for t in MESSAGE_TYPES}
        self.processor = FlowProcessor()
        self.origin: tuple[float, float] | None = None
        self.flow_valid = False
        self.flow_distance: float | None = None
        self.flow_distance_source: str | None = None
        self.range_distance: float | None = None
        self.range_time: float | None = None
        self.invalid_packets = 0
        self.system_id: int | None = None
        self.stale_reported: set[str] = set()
        self.revision += 1

    def event(self, text: str, level: str = "INFO") -> None:
        with self.lock:
            self.events.append({"timestamp": time.time(), "message": text, "level": level})
        getattr(logger, level.lower(), logger.info)(text)

    def transition(self, state: str, error: str | None = None) -> None:
        with self.lock:
            if self.state != state or self.error != error:
                self.state, self.error = state, error
                self.event(error or state.replace("_", " "), "ERROR" if error else "INFO")

    def reset_origin(self) -> None:
        with self.lock:
            p = self.raw.get("LOCAL_POSITION_NED", {})
            self.origin = (p["x"], p["y"]) if finite(p.get("x"), p.get("y")) else None
            self.processor.reset()
            self.flow_valid = False
            self.revision += 1
            self.event("Origin reset (local display only)")

    def update_settings(self, settings: Settings) -> None:
        with self.lock:
            old = self.settings
            self.settings = settings
            if old.source != settings.source:
                self.revision += 1
            if any(getattr(old, k) != getattr(settings, k) for k in
                   ("flow_input", "swap_xy", "invert_x", "invert_y", "rotation", "yaw_compensation", "gyro_compensation")):
                self.processor.reset()
                self.flow_valid = False
                self.revision += 1
                self.event("Flow axes changed; integrated flow origin restarted")

    def report_stale(self) -> None:
        """Log only the transition to stale, never every broadcast frame."""
        now = time.monotonic()
        with self.lock:
            for kind in ("OPTICAL_FLOW", "OPTICAL_FLOW_RAD", "DISTANCE_SENSOR", "LOCAL_POSITION_NED", "ATTITUDE"):
                last = self.times.get(kind)
                if last is not None and now - last > DATA_TIMEOUT:
                    if kind not in self.stale_reported:
                        self.stale_reported.add(kind)
                        self.event(f"{kind} telemetry stale", "WARNING")
                else:
                    self.stale_reported.discard(kind)

    def ingest(self, kind: str, raw: dict, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self.lock:
            if kind not in self.rates:
                return
            first = kind not in self.times
            self.raw[kind] = clean(raw)
            self.times[kind] = now
            self.rates[kind].append(now)
            if first:
                self.event(f"{kind} received")
            if kind == "HEARTBEAT":
                self.transition("CONNECTED")
            elif kind == "DISTANCE_SENSOR":
                # DISTANCE_SENSOR is centimeters; only downward facing (25)
                # measurements within the sensor's declared bounds are ground range.
                cm = raw.get("current_distance")
                valid = (raw.get("orientation") == 25 and finite(cm, raw.get("min_distance"), raw.get("max_distance"))
                         and raw["min_distance"] <= cm <= raw["max_distance"] and 0 < cm < 65535)
                self.range_distance = cm / 100 if valid else None
                self.range_time = now
            elif kind == "LOCAL_POSITION_NED":
                if self.origin is None and finite(raw.get("x"), raw.get("y")):
                    self.origin = (raw["x"], raw["y"])
            elif kind in ("OPTICAL_FLOW_RAD", "OPTICAL_FLOW"):
                if kind != ("OPTICAL_FLOW" if self.settings.flow_input == "mission_planner" else "OPTICAL_FLOW_RAD"):
                    return  # never integrate both streams for the same motion
                # Flow.distance is already METERS; reject stale distance samples.
                d = raw.get("ground_distance" if kind == "OPTICAL_FLOW" else "distance")
                distance_age = raw.get("time_delta_distance_us", 0)
                self.flow_distance_source = kind
                if kind == "OPTICAL_FLOW":
                    # ArduPilot legacy ground_distance is EKF HAGL, not guaranteed
                    # to be a direct sensor measurement. Prefer measured RAD range
                    # or downward DISTANCE_SENSOR; never silently use EKF altitude.
                    rad = self.raw.get("OPTICAL_FLOW_RAD", {})
                    d = rad.get("distance") if now - self.times.get("OPTICAL_FLOW_RAD", -1e9) <= DATA_TIMEOUT else None
                    distance_age = rad.get("time_delta_distance_us", 0)
                    self.flow_distance_source = "OPTICAL_FLOW_RAD"
                if not (finite(d, distance_age) and d > 0 and 0 <= distance_age <= 1_000_000):
                    d = self.range_distance if self.range_time is not None and now - self.range_time <= DATA_TIMEOUT else None
                    self.flow_distance_source = "DISTANCE_SENSOR" if d is not None else None
                self.flow_distance = d
                att = self.raw.get("ATTITUDE", {})
                yaw = att.get("yaw") if now - self.times.get("ATTITUDE", -1e9) <= DATA_TIMEOUT else None
                yaw = yaw if finite(yaw) else None
                self.flow_valid = (self.processor.integrate_rates(raw, now, d, yaw, self.settings)
                                   if kind == "OPTICAL_FLOW" else self.processor.integrate(raw, d, yaw, self.settings))
                if not self.flow_valid:
                    self.invalid_packets += 1

    def snapshot(self, now: float | None = None) -> dict:
        now = time.monotonic() if now is None else now
        with self.lock:
            hb_age = age(self.times.get("HEARTBEAT"), now)
            connected = self.state == "CONNECTED" and hb_age is not None and hb_age <= HEARTBEAT_TIMEOUT
            kind = "OPTICAL_FLOW" if self.settings.flow_input == "mission_planner" else "OPTICAL_FLOW_RAD"
            flow = copy.deepcopy(self.raw.get(kind, {}))
            legacy = self.raw.get("OPTICAL_FLOW", {})
            flow_age = age(self.times.get(kind), now)
            fields = ("flow_comp_m_x", "flow_comp_m_y") if kind == "OPTICAL_FLOW" else ("integrated_x", "integrated_y")
            flow_status = data_status(self.times.get(kind), now, finite(*(flow.get(k) for k in fields)))
            if flow_status == "ACTIVE" and (flow.get("quality") or 0) <= 120:
                flow_status = "LOW QUALITY"
            flow_kind = kind
            debug = {}
            for kind in MESSAGE_TYPES:
                samples = [t for t in self.rates[kind] if now - t <= 3]
                hz = (len(samples) - 1) / (samples[-1] - samples[0]) if len(samples) >= 2 and samples[-1] > samples[0] else 0
                debug[kind] = {"age_ms": None if kind not in self.times else (now - self.times[kind]) * 1000,
                               "rate_hz": hz, "last_timestamp": None if kind not in self.times else time.time() - (now - self.times[kind])}
            flow.update(status=flow_status, age_ms=None if flow_age is None else flow_age * 1000,
                        rate_hz=debug[flow_kind]["rate_hz"], input_message=flow_kind,
                        opt_m_x=legacy.get("flow_comp_m_x"), opt_m_y=legacy.get("flow_comp_m_y"),
                        opt_status=data_status(self.times.get("OPTICAL_FLOW"), now,
                                              finite(legacy.get("flow_comp_m_x"), legacy.get("flow_comp_m_y"))),
                        ground_distance=self.flow_distance, distance_source=self.flow_distance_source)
            att = self.raw.get("ATTITUDE", {})
            attitude = {k: math.degrees(att[k]) if finite(att.get(k)) else None for k in ("roll", "pitch", "yaw")}
            if attitude["yaw"] is not None:
                attitude["yaw"] %= 360
            attitude["status"] = data_status(self.times.get("ATTITUDE"), now)
            local = self.raw.get("LOCAL_POSITION_NED", {})
            local_live = data_status(self.times.get("LOCAL_POSITION_NED"), now) == "ACTIVE"
            available = False
            velocity = {"vx": None, "vy": None, "speed": None}
            if self.settings.source == "local_position":
                available = connected and local_live and self.origin is not None and finite(local.get("x"), local.get("y"))
                pos = ned_position(local["x"], local["y"], self.origin) if self.origin and finite(local.get("x"), local.get("y")) else None
                if available and finite(local.get("vx"), local.get("vy")):
                    velocity = {"vx": local["vx"], "vy": local["vy"], "speed": math.hypot(local["vx"], local["vy"])}
                reason = "Recent valid LOCAL_POSITION_NED required"
            else:
                available = connected and self.flow_valid and flow_age is not None and flow_age <= DATA_TIMEOUT
                pos = ned_position(self.processor.north, self.processor.east, (0, 0))
                if available and self.processor.velocity:
                    vn, ve = self.processor.velocity
                    velocity = {"vx": vn, "vy": ve, "speed": math.hypot(vn, ve)}
                reason = "Recent flow, quality > 0, valid ground distance and heading required"
            position = {**(pos or {"north": None, "east": None, "x": None, "y": None, "distance": None}),
                        "source": self.settings.source, "available": available, "reason": None if available else reason}
            return clean({"timestamp": time.time(), "state": self.state, "connected": connected,
                          "heartbeat": connected, "heartbeat_age_ms": None if hb_age is None else hb_age * 1000,
                          "simulation": self.simulation, "port": self.port, "baud": self.baud, "error": self.error,
                          "system_id": self.system_id, "revision": self.revision, "position": position,
                          "flow": flow, "legacy_flow": self.raw.get("OPTICAL_FLOW"),
                          "rangefinder": {"distance": self.range_distance, "status": data_status(self.range_time, now, self.range_distance is not None)},
                          "attitude": attitude, "velocity": velocity, "debug": debug,
                          "invalid_packets": self.invalid_packets, "sys_status": self.raw.get("SYS_STATUS"),
                          "settings": self.settings.model_dump(), "events": list(self.events)})
