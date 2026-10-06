# Optical Flow Drone Movement Visualizer

A localhost read-only ArduPilot telemetry dashboard for inspecting optical flow,
rangefinder readings, attitude, and estimated North/East movement. Use a USB-connected
flight controller or the built-in hardware-free simulation.

Python owns one Windows
COM port, parses MAVLink in a dedicated thread, and sends 25 Hz snapshots over
WebSocket. React renders the movement map using a resize-aware Canvas. Multiple
tabs can view the same connection. Refreshing a browser never opens a serial port.

## Features

- Live movement map with heading, bounded trails, origin reset, and test boundaries.
- Optical-flow integration or EKF local-position display, with explicit stale-data status.
- Sensor mounting corrections, yaw transforms, and optional velocity filtering.
- Serial-port discovery, heartbeat monitoring, and MAVLink diagnostics.
- Automatic and keyboard-controlled simulation isolated from serial hardware.
- Local FastAPI backend and React/TypeScript frontend; no cloud account required.

The only outbound MAVLink command is `MAV_CMD_SET_MESSAGE_INTERVAL`, used to
request telemetry rates. The dashboard has no vehicle-control functions.

## Vercel deployment

Live site: **https://optical-flow-visualizer.vercel.app**. Connect your flight
controller with **Connect USB**, or click **Start simulation** without hardware.
The Vercel project is connected to this GitHub repository for automatic
deployments when changes are pushed.

Import this repository as one Vercel project with Root Directory `.`. The root
`vercel.json` defines two independently built services: `app` (FastAPI, entrypoint
`backend/cloud.py`) and `frontend` (Vite). `/api/*` routes to `app`; all other
paths route to `frontend`. Neither service calls the other server-side, so no
internal bindings or manually configured binding variables are needed.

### USB directly from the hosted site

1. Open the site in desktop **Chrome or Edge** over HTTPS.
2. Connect the flight controller with a data-capable USB cable.
3. Close Mission Planner, MAVProxy and other applications using its serial port.
4. Select the baud rate (default 115200), click **Connect USB**, and select your
   flight controller in the browser's device picker.
5. Wait for **HEARTBEAT OK**, then confirm real flow and measured range readings.
6. Use Reset origin and the map controls. Click Disconnect when finished.

Web Serial reads the selected device on your own computer; no local server or
Python installation is needed for this mode. MAVLink telemetry packets are sent
over HTTPS to `/api/usb/step` for checksum validation and the existing Python
sensor transforms. Browser-owned state keeps visitors isolated across Vercel
instances. Only telemetry interval requests (`MAV_CMD_SET_MESSAGE_INTERVAL`) can
be written to USB. The browser also checks this command allowlist before writing.
The server never opens a serial port and never controls the vehicle.

The site does not automatically restore USB permission or reopen a port after
refresh, unplugging, heartbeat loss, or backend failure. Connect again explicitly.
Firefox, Safari and browsers without Web Serial can use simulation or the local
launcher. The device must expose a serial/MAVLink endpoint, not a bootloader.

### Hosted simulation

Click **Start simulation** to see generated movement; manual directions, axis
corrections, origin reset and map controls work. USB must be disconnected first.
Each browser owns its session and submits it to a stateless API. Closing/reloading
resets the session. HTTP display updates run at up to 5 Hz; all received USB
samples retain their receive times and are processed individually. Canvas
animation remains independent. No database, WebSocket server, server serial
worker, or manually configured environment variables are required.

To test services routing locally with a current Vercel CLI, run `vercel dev -L`
from the repository root. To publish, run `vercel` for preview and `vercel --prod`
for production, or connect the GitHub repository in the Vercel dashboard.

## Local requirements

- Windows 10/11, Python 3.11 or newer (tested here with 3.14).
- Node.js 22 LTS (22.12+) or newer for frontend installation/build.
- Internet on first setup for Python/npm packages. Later launches use cached installs.
- ArduPilot FC exposing MAVLink over USB; optical flow and a valid ground range
  are required for metric flow integration. Simulation needs no hardware.

## Quick start

Double-click **start.bat** in this folder. It checks Python/Node, creates `.venv`,
installs missing/changed dependencies, builds the frontend when source changes,
starts FastAPI at **http://127.0.0.1:8000**, and opens your browser after readiness.
It does not reinstall everything on each launch. Keep its console open; Ctrl+C
stops the server and releases the COM port. A project-local Node under `.tools`
is supported if Node is absent from PATH.

```powershell
# From the cloned repository folder:
.\start.bat
```

To develop with Vite hot reload:

```powershell
python scripts\run_dev.py --dev
# Browser: http://127.0.0.1:5173
```

## Installation (manual)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For two-terminal development, run the same backend command and `npm run dev`
inside `frontend`. Vite proxies `/api` and `/ws` to the backend. Both bind only to
127.0.0.1. The API rejects untrusted browser origins; no cloud service is involved.

## Connecting Drone

1. Connect the flight controller using USB.
2. Open Windows Device Manager, Ports (COM & LPT).
3. Find its COM port. COM10 and higher work through pyserial without manual paths.
4. Start the application.
5. Click Refresh ports and select the detected COM port.
6. Select baud (default 115200; also 57600, 230400, 460800, 921600).
7. Press Connect.
8. Wait for **MAVLink heartbeat received**. Opening serial alone is not connection.
9. Confirm OPTICAL_FLOW_RAD messages in Optical flow and MAVLink debug.
10. Press Reset origin.
11. Move the drone horizontally and observe the map, North/East and trail.

Connection progresses through DISCONNECTED, CONNECTING,
WAITING_FOR_HEARTBEAT, CONNECTED, CONNECTION_LOST or ERROR. Initial heartbeat
timeout is 12 seconds; an established heartbeat is lost after 5 seconds. After
loss the reader closes serial. Reconnect explicitly; no automatic reconnect.

## Simulation

With no connection, press **Start simulation**. The amber SIMULATION banner
and status identify generated telemetry. Automatic motion makes curves with
forward/right/back/left components, changing heading, distance and quality.
All map, origin, source and trail controls work. Enable Manual movement to hold
W/A/S/D or the direction buttons. Directions refer to map North/East, not a
vehicle command. Keyboard controls ignore text inputs. Input expires after
0.5 seconds if the browser goes away. Disconnect ends simulation.

Simulation is entirely in the Python backend, never opens serial, and never
sends MAVLink messages. Manual controls exist only during simulation.

## Coordinate system and estimate limitations

All metric processing lives in `backend/flow_processor.py`:

- LOCAL_POSITION_NED **x = North**, **y = East**, **z = Down** (meters).
- Map/display **X = East**, **Y = North**. `worldToScreen(east,north)` computes
  `centerX + east*scale`, `centerY - north*scale`, because screen Y points down.
- ATTITUDE values arrive in radians, are displayed in degrees, and yaw is
  normalized to 0–360°. Heading 0 points up, 90 points right.
- OPTICAL_FLOW_RAD integrated values are radians accumulated over one interval.
  They are never treated as meters or multiplied by the interval a second time.
  The [MAVLink definition](https://mavlink.io/en/messages/common.html#OPTICAL_FLOW_RAD)
  specifies rotation about axes: positive flow Y corresponds to forward sensor
  translation; positive flow X corresponds to negative rightward translation.
- Default assumptions: downward-looking sensor, sensor X forward, Y right.
  Gyro-compensated angular values are `flow_x - gyro_x`, `flow_y - gyro_y`.
  Forward displacement = `distance * corrected_flow_y`; right displacement =
  `-distance * corrected_flow_x`. This is a small-angle approximation.
- Swap, invert and clockwise mounting rotation apply to sensor forward/right,
  **before** body yaw maps into world North/East. Invert X means forward,
  Invert Y means right. Changes restart the flow origin/trail to avoid mixing frames.
- World-relative yaw is enabled by default and needs fresh ATTITUDE. Disable it
  to debug body-frame movement with a fixed initial North/forward assumption.
- Roll/pitch terrain projection is not implemented. Heavy tilt, sensor mounting,
  gyro mismatch, yaw error and distance error degrade the flow estimate. The
  separate transform functions make future attitude compensation possible.
- Prefer positive finite OPTICAL_FLOW_RAD.distance **in meters**, with sample
  age at most one second. Otherwise use recent downward-facing DISTANCE_SENSOR
  (orientation 25), bounds-checked and converted **centimeters → meters**.
  No barometer/GPS/other altitude substitution occurs. Without distance the raw
  packet remains visible, but metric position is unavailable.
- Zero-quality packets, invalid values, duplicate sensor/timestamp samples,
  intervals outside 0–1 second, angular jumps over 0.5 rad and estimates over
  15 m/s are rejected. These debug-oriented bounds suit hand motion and slow tests.
  Displacement rejected or missed during stale data is not reconstructed later.
- Default input is Mission Planner **opt_m_x / opt_m_y**, mapped directly to
  OPTICAL_FLOW.flow_comp_m_x / flow_comp_m_y. ArduPilot fills these legacy fields
  with gyro-corrected angular rates in **rad/s**, despite MAVLink's m/s field label.
  See [Mission Planner's mapping](https://github.com/ArduPilot/MissionPlanner/blob/master/ExtLibs/ArduPilot/CurrentState.cs)
  and [ArduPilot's send_opticalflow](https://github.com/ArduPilot/ardupilot/blob/master/libraries/GCS_MAVLink/GCS_Common.cpp).
  Displacement uses rate × monotonic receive interval × measured ground distance.
  Do not subtract gyro twice or treat the values as positions. ArduPilot uses
  milliseconds in the legacy time_usec field, so it is only a duplicate identifier.
  The first sample and gaps over one second establish a baseline without motion.
- ArduPilot legacy ground_distance is EKF HAGL, not necessarily a direct
  measurement. This application uses fresh RAD distance or downward
  DISTANCE_SENSOR instead. Without measured range, opt_m values remain visible
  but metric position is unavailable.
- Select OPTICAL_FLOW_RAD in Axis corrections & display settings to use
  accumulated angles instead. Only the selected stream contributes movement;
  receiving both never doubles displacement. Switching input restarts the
  integrated origin/trail. EKF mode works independently.
- OFF/LOW/MEDIUM filtering applies an EMA to velocity, **not accumulated
  displacement**, so mild filtering cannot silently erase distance. Optional
  per-sample angular deadband defaults OFF, threshold 0.0002 rad.

Quality labels POOR (0–50), LOW (51–120), OK (121–200), GOOD (201–255)
are visualization labels only. Flow/rangefinder/attitude/local position age
exceeding one second is stale. A lost backend greys the map marker and labels
the values as stale/offline. Historical positions remain visible with unavailable
status; they do not count as new live trail samples.

## Map controls

- Reset origin: locally saves current NED North/East and resets integrated flow
  displacement, clearing the displayed trail. No FC state is reset.
- Clear trail: clears this browser's history, preserving connection and origin.
- Pause visualization: freezes this browser's marker/trail, while telemetry and
  backend integration continue. Resume shows the latest position.
- Position source: changes processing mode without disconnecting; restarts trail.
- Auto scale fits trail/current position/boundary. Fixed ±0.5, 1, 2, 5, 10, 20,
  50 m scales intentionally permit movement off-screen; return to Auto to fit.
  Scale is the smaller axis extent; a wide canvas shows more East/West area.
- Optional test boundary: width/height in meters, centered on origin. Leaving
  it displays OUTSIDE TEST AREA and does not affect processing.
- Trail: bounded to 10,000 points, sampled by movement/time and downsampled
  when full. Old positions remain represented without unlimited memory growth.

Baud, map scale, trail, boundary, smoothing and axis preferences are stored in
localStorage. Live backend settings win when opening another tab. Serial
connection is never restored automatically. Origin/source/settings are global
to the backend; pause/clear trail/map preferences are per-browser. A server
restart resets all live telemetry and connection, and WebSocket reconnects.

## MAVLink and concurrency

The single serial worker uses actual pymavlink `mavlink_connection` and
nonblocking `recv_match`; FastAPI never blocks on serial. An RLock protects
telemetry state and a lifecycle lock serializes connect/disconnect. The reader
closes its own port in `finally`. Heartbeat identifies a flight controller,
filters out GCS/component heartbeats, and selects one vehicle system.

After its first valid heartbeat, the backend requests message intervals once:
ATTITUDE 20 Hz, LOCAL_POSITION_NED 15 Hz, OPTICAL_FLOW_RAD 20 Hz,
OPTICAL_FLOW 10 Hz, DISTANCE_SENSOR 15 Hz and SYS_STATUS 1 Hz. Unsupported
requests/negative acknowledgements are logged without crashing. See the
[MAVLink interval protocol](https://mavlink.io/en/services/command.html).

The only outbound command is **MAV_CMD_SET_MESSAGE_INTERVAL**. There are no
arming, flight-mode, motor, mission, RC or actuator controls. Snapshot parsing
and Canvas animation are decoupled; React widgets update at 5 Hz. Slow WebSocket
clients time out independently. Shutdown stops broadcast, closes clients,
signals the reader, joins it, and closes serial. Do not use multiple Uvicorn
workers: they would create separate serial owners.

## API

Interactive schemas: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
|---|---|
| GET /api/health | Backend/read-only health |
| GET /api/ports | Detected serial ports |
| GET /api/status | Full telemetry snapshot |
| POST /api/connect | `{ "port": "COM3", "baud": 115200 }` (select actual port) |
| POST /api/disconnect | Stop reader/simulation |
| POST /api/reset-origin | Local origin reset |
| POST /api/settings | Validated complete processing settings |
| POST /api/simulation/start | Start generated telemetry |
| POST /api/simulation/input | Simulation-only manual/automatic input |
| WS /ws/telemetry | 25 Hz JSON snapshots |

`position.x` is East; `position.y` is North. `velocity.vx` is NED North,
`velocity.vy` NED East. Numeric invalid/missing fields are null, never NaN/Infinity.
Python settings model and TypeScript interface have matching fields.

## Troubleshooting

### COM port not appearing

Use a data-capable USB cable. Check Device Manager and the board's driver.
Click Refresh ports after plugging in. The list comes from serial.tools.list_ports,
not a hardcoded port. If Device Manager has no port, the website cannot invent one.

### Access denied / port busy

Close Mission Planner, MAVProxy, Arduino Serial Monitor or other serial tools.
Usually only one program can own the serial port directly at a time. Disconnect
in this application before giving another program the port. Run one backend only.

### MAVLink heartbeat not detected

Confirm the selected port/baud and that the FC's USB/serial endpoint sends MAVLink,
not a bootloader or console stream. The UI waits 12 seconds, then reports ERROR.
Check the event log. Try another baud and reconnect. Interval requests happen only
after heartbeat and cannot enable a non-MAVLink serial endpoint.

### Optical flow says NO DATA

Look at OPTICAL_FLOW for the default Mission Planner input, or OPTICAL_FLOW_RAD
if that input is selected. The sensor may be configured but not
forwarded by firmware on this link, or the interval request may be unsupported.
Verify ArduPilot sensor/telemetry configuration separately. If Mission Planner
shows opt_m_x/y while RAD is absent, select the Mission Planner flow input.
No sensor message is fabricated. Raw data continues even if position is unavailable.

### Rangefinder says NO DATA

Verify DISTANCE_SENSOR messages, sensor orientation and declared limits.
Only downward-facing sensor readings qualify here. Optical-flow distance may
be valid while the separate rangefinder panel has no data; it is never substituted.
Invalid/out-of-range DISTANCE_SENSOR shows INVALID; old measurements show STALE.

### Dot moves opposite direction

Test one direction at a time with yaw/gyro settings understood. Use Invert X
(sensor forward), Invert Y (sensor right), Swap X/Y, or 0/90/180/270° mounting
rotation. Corrections are applied before yaw. Changing transforms resets the
flow origin automatically. Map remains North up/East right. Check heading first
if body-forward appears sideways in world-relative mode.

### Trail moves but drone is stationary

Raw flow integration drifts. Inspect quality, distance, raw flow and attitude.
Try the optional conservative deadband. Velocity filtering improves readability
without removing integrated distance; it is not a solution for sensor bias.
Do not interpret quality labels as flight readiness.

### Incorrect distance

Metric flow displacement scales directly with measured ground distance. Inspect
the actual flow/rangefinder values. Units are meters for flow and centimeters
on the DISTANCE_SENSOR wire. Wrong range, sloped surfaces or tilt affect estimates.

### USB unplug / reconnect

Serial failure or heartbeat timeout shows CONNECTION LOST and leaves the server
running. Reinsert USB, refresh ports, select the actual port, and press Connect.
Stale telemetry remains labeled; reconnection starts fresh telemetry/origins.

### Backend restart / browser refresh

WebSocket retries every 1.5 seconds. Refresh never reconnects the FC. Restarting
the backend closes serial and requires an explicit Connect. If 8000/5173 is busy,
the launcher reports it rather than silently opening another instance.

## Tests and acceptance checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run typecheck
npm test
npm run build
```

Tests cover NED/screen axes, yaw, distance and units, duplicate prevention,
flow displacement, gyro subtraction, inversion/swap/rotations, transform order,
origin reset, filtering, stale data, rejected packets, APIs and live simulation
WebSocket/shutdown. Serial tests encode/decode actual pymavlink packets with a
mock transport, check COM10 handling, busy errors, unplug/reconnect and heartbeat
timeout. No lint tool is configured; strict TypeScript and builds run.

For an acceptance smoke check against the running production server (disconnect
any vehicle first): `.\.venv\Scripts\python.exe scripts\smoke_test.py`.
This explicitly starts simulation, checks the real HTTP/WebSocket transport,
and stops it afterward. It never opens a COM port.

For development-server compilation/proxy checks with `--dev` running:
`.\.venv\Scripts\python.exe scripts\check_dev.py` (leave the vehicle disconnected).

Hardware acceptance: connect actual FC; confirm heartbeat, raw RAD and rangefinder;
reset and move in known North/East directions; check sign/mounting corrections;
unplug to see connection loss; reconnect. Tests and simulation cannot prove
physical sensor calibration, firmware streams or real flight behavior.

## Project layout

```text
backend/                 FastAPI API, serial reader, telemetry, and simulation
  flow_processor.py      Sensor transforms and movement integration
frontend/src/            React dashboard, Canvas map, and WebSocket client
frontend/tests/          Map-coordinate tests
tests/                   Backend, API, processing, and mocked serial tests
scripts/run_dev.py       Dependency bootstrap and server launcher
scripts/smoke_test.py    HTTP/WebSocket simulation acceptance check
scripts/check_dev.py     Development compilation and proxy checks
docs/VALIDATION.md       Recorded validation evidence and remaining limitations
start.bat                Windows one-click launcher
```

See [validation evidence](docs/VALIDATION.md) for recorded checks and limitations.
Hardware observations there describe a previous session, not the current
connection or proof of physical movement accuracy.

## Contributing

Keep all sensor transforms in `backend/flow_processor.py`, preserve the
North/East coordinate conventions, and keep simulation independent of serial.
Do not introduce vehicle-control commands or automatic serial reconnection.
Run the backend tests, frontend typecheck, frontend tests, and production build
before submitting changes. Project-specific guidance is in [AGENTS.md](AGENTS.md).
