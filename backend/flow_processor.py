"""All metric/axis math lives here. No pixels, no flight-controller writes.

NED x = North, y = East, z = Down. Display x = East, y = North.
OPTICAL_FLOW_RAD is rotation about sensor axes, NOT translation along them:
positive integrated_y means +sensor X translation; positive integrated_x
means -sensor Y translation (MAVLink common.xml). Assume downward-looking
sensor, X forward, Y right. Subtract sensor gyro angular displacement first.
Then map forward = distance * corrected_y, right = -distance * corrected_x.
User transforms act on this sensor translation (X forward / Y right), BEFORE
yaw rotates body forward/right into world North/East. Positive mounting
rotation is clockwise seen from above. Small-angle approximation, meters and
radians. No roll/pitch terrain projection; tilt degrades this debug estimate.
"""
import math
from .models import Settings

def finite(*values: object) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)

def sensor_transform(forward: float, right: float, settings: Settings) -> tuple[float, float]:
    if settings.swap_xy:
        forward, right = right, forward
    if settings.invert_x:
        forward = -forward
    if settings.invert_y:
        right = -right
    a = math.radians(settings.rotation)
    return forward * math.cos(a) - right * math.sin(a), forward * math.sin(a) + right * math.cos(a)

def body_to_world(forward: float, right: float, yaw: float) -> tuple[float, float]:
    return forward * math.cos(yaw) - right * math.sin(yaw), forward * math.sin(yaw) + right * math.cos(yaw)

def ned_position(north: float, east: float, origin: tuple[float, float]) -> dict[str, float]:
    n, e = north - origin[0], east - origin[1]
    return {"north": n, "east": e, "x": e, "y": n, "distance": math.hypot(n, e)}


def simulated_packets(t: float, dt: float, north: float, east: float, vn: float, ve: float):
    """Generate sensor-axis samples from world motion for the stateless demo."""
    yaw = math.atan2(ve, vn) if vn or ve else 0.0
    distance = 1.5 + 0.08 * math.sin(t)
    forward = vn * math.cos(yaw) + ve * math.sin(yaw)
    right = -vn * math.sin(yaw) + ve * math.cos(yaw)
    return [
        ("HEARTBEAT", {"autopilot": 3, "type": 2}),
        ("ATTITUDE", {"roll": 0.02 * math.sin(t), "pitch": 0.015 * math.cos(t), "yaw": yaw}),
        ("DISTANCE_SENSOR", {"current_distance": round(distance * 100), "min_distance": 10,
                             "max_distance": 1000, "orientation": 25}),
        ("LOCAL_POSITION_NED", {"x": north, "y": east, "z": -distance, "vx": vn, "vy": ve}),
        ("OPTICAL_FLOW_RAD", {"time_usec": round(t * 1e6), "sensor_id": 0,
            "integration_time_us": dt * 1e6, "integrated_x": -right * dt / distance,
            "integrated_y": forward * dt / distance, "integrated_xgyro": 0, "integrated_ygyro": 0,
            "quality": 225, "distance": distance, "time_delta_distance_us": 0}),
        ("OPTICAL_FLOW", {"time_usec": round(t * 1e6), "sensor_id": 0,
            "flow_comp_m_x": -right / distance, "flow_comp_m_y": forward / distance,
            "quality": 225, "ground_distance": distance}),
    ]

class FlowProcessor:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.north = self.east = 0.0
        self.velocity: tuple[float, float] | None = None
        self.last_stamp: tuple[int, int] | None = None
        self.rate_time: float | None = None
        self.rate_stamp: tuple[int, int] | None = None

    def integrate_rates(self, raw: dict, now: float, distance: float | None,
                        yaw: float | None, settings: Settings) -> bool:
        """ArduPilot OPTICAL_FLOW flow_comp_m_x/y (Mission Planner opt_m_x/y).

        ArduPilot GCS_MAVLink sends flowRate - bodyRate, in rad/s, in these
        legacy fields despite common.xml's m/s label. Do NOT interpret them as
        meters or subtract gyro again. Integrate using backend monotonic receive
        intervals: ArduPilot's legacy time_usec is populated with milliseconds,
        so it is used only as a duplicate identifier, never as a time duration.
        First sample and gaps >1s establish a new baseline without displacement.
        This path is explicitly ArduPilot-specific, not a generic MAVLink parser.
        """
        stamp = (raw.get("sensor_id", 0), raw.get("time_usec", 0))
        if stamp == self.rate_stamp:
            return False
        previous = self.rate_time
        self.rate_time, self.rate_stamp = now, stamp
        if previous is None or not 0 < now - previous <= 1:
            return False
        x, y = raw.get("flow_comp_m_x"), raw.get("flow_comp_m_y")
        if not finite(x, y):
            return False
        dt = now - previous
        sample = {"integrated_x": x * dt, "integrated_y": y * dt,
                  "integration_time_us": dt * 1e6, "integrated_xgyro": 0,
                  "integrated_ygyro": 0, "quality": raw.get("quality"),
                  "sensor_id": stamp[0], "time_usec": stamp[1]}
        return self.integrate(sample, distance, yaw, settings)

    def integrate(self, raw: dict, distance: float | None, yaw: float | None, settings: Settings) -> bool:
        x, y, dt_us = raw.get("integrated_x"), raw.get("integrated_y"), raw.get("integration_time_us")
        if not finite(x, y, dt_us, distance) or distance <= 0 or not 0 < dt_us <= 1_000_000:
            return False
        if not finite(raw.get("quality")) or raw["quality"] <= 0:
            return False
        stamp = (raw.get("sensor_id", 0), raw.get("time_usec", 0))
        if stamp == self.last_stamp:
            return False  # never integrate the same sample twice
        self.last_stamp = stamp
        if settings.yaw_compensation and yaw is None:
            return False
        gx, gy = raw.get("integrated_xgyro"), raw.get("integrated_ygyro")
        if settings.gyro_compensation and finite(gx, gy):
            x, y = x - gx, y - gy
        if settings.deadband:
            x = 0.0 if abs(x) < settings.deadband_rad else x
            y = 0.0 if abs(y) < settings.deadband_rad else y
        # Reject >0.5 rad per sample or >15 m/s estimated single-frame speed.
        dt = dt_us / 1_000_000
        if max(abs(x), abs(y)) > 0.5:
            return False
        f, r = sensor_transform(distance * y, -distance * x, settings)
        n, e = body_to_world(f, r, (yaw or 0) if settings.yaw_compensation else 0)
        if math.hypot(n, e) / dt > 15:
            return False
        # Integrate unfiltered displacement exactly once. EMA affects displayed
        # velocity only, preserving distance even with varying message intervals.
        self.north += n
        self.east += e
        vn, ve = n / dt, e / dt
        alpha = {"OFF": 1.0, "LOW": 0.65, "MEDIUM": 0.35}[settings.smoothing]
        old = self.velocity or (vn, ve)
        self.velocity = (old[0] + alpha * (vn - old[0]), old[1] + alpha * (ve - old[1]))
        return True
