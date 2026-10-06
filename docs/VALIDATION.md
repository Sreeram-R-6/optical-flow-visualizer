# Validation evidence

## Hosted browser USB — 2026-10-06

- USB support deployed to https://optical-flow-visualizer.vercel.app, commit b09e825.
- Browser Web Serial opens the selected device only after Connect USB is clicked.
  No local server is needed. Browser-selected USB bytes are decoded by pymavlink
  in `/api/usb/step`; transforms remain in `backend/flow_processor.py`.
- 39 backend tests and 8 frontend tests pass, plus TypeScript checking and build.
  Coverage includes MAVLink 1/2 decoding, checksum rejection, large sensor
  timestamps, legacy flow across stateless requests, origin reset, heartbeat
  timeout, unrelated vehicle filtering, USB unplug and cancellation, stream-lock
  cleanup, and blocking outbound commands other than SET_MESSAGE_INTERVAL.
- Production browser test used a **mock Web Serial device** emitting real
  pymavlink-encoded frames through the deployed UI and API. It reached CONNECTED /
  HEARTBEAT OK, displayed Browser USB / 115200, North 1.050 m / East 0.000 m,
  and showed no simulation banner or application errors.
- The mock captured exactly six outbound COMMAND_LONG packets, all command 511
  (SET_MESSAGE_INTERVAL). It observed one picker call and one port open, then one
  close after heartbeat loss, with explicit reconnect available and no auto reopen.
- These checks prove the deployed software path with a mock transport. They do
  not prove a physical browser/device/driver connection, mounting direction or
  sensor calibration. Serial-port discovery reported no available devices during
  this run. Physical USB acceptance remains outstanding.

## Vercel services deployment — 2026-10-06

- Production: https://optical-flow-visualizer.vercel.app.
- GitHub integration connected to Sreeram-R-6/optical-flow-visualizer.
- Vercel built the Vite frontend and FastAPI `backend/cloud.py` entrypoint.
- Public `/api/*` targets `app`; the catch-all targets `frontend`. No internal
  service calls or bindings are required.
- 33 backend tests, 4 frontend tests, TypeScript checking and frontend build passed.
- `vercel dev -L` successfully served both services from a clean temporary checkout.
  The original workspace has an inaccessible historical `.pytest_cache` directory;
  the CLI also required a precreated virtual environment to avoid the Windows
  `python3` Microsoft Store alias. These are local machine issues, not cloud failures.
- Live unauthenticated `/api/health` returned the hosted-demo mode.
- Browser verified simulation start, visible changing positions, manual North input
  (North increased, East stayed zero), origin reset to zero and simulation stop.
- Live stateless API verified North displacement from 0.16 m to 0.32 m over two
  steps and an independent empty session remaining disconnected.
- Hosted simulation uses browser-owned session state and bounded HTTP updates;
  the cloud entrypoint exposes no serial connection route. USB telemetry remains
  available through the local launcher.
- No physical-device checks were performed during this deployment.

Implemented and checked on Windows, 2026-10-06.

## Passed

- Python 3.14 virtual environment and required packages installed.
- 31 backend pytest cases: coordinate transforms, range units/fallback, origin,
  gyro, yaw, invalid/duplicate packets, stale data, filtering, simulation/API,
  actual pymavlink packet encoding/decoding with mocked serial, port busy,
  COM10 input, USB loss/reconnect, heartbeat timeout and shutdown.
- Follow-up: Mission Planner mapping and ArduPilot sender source verified.
  ArduPilot legacy fields carry corrected angular rates, so displacement uses
  range × rate × monotonic elapsed time, with no second gyro subtraction.
- Follow-up live COM3 at 115200: heartbeat received, OPTICAL_FLOW ~10 Hz,
  DISTANCE_SENSOR ~15 Hz, ATTITUDE ~20 Hz and LOCAL_POSITION_NED ~15 Hz.
  No OPTICAL_FLOW_RAD received. Snapshot opt_m_x/y exactly matched incoming
  flow_comp_m_x/y; measured range was 0.14 m in one snapshot and integrated
  position was available using DISTANCE_SENSOR. Server remains connected.
- Three frontend tests execute compiled production map math.
- Strict TypeScript typecheck.
- Vite 8 production build; dependency audit reported zero vulnerabilities.
- Production launcher started backend and served built HTML/JS over HTTP.
- Live smoke test passed simulation, WebSocket movement, range, local reset,
  axis settings, rotation, source switch, manual input and stop.
- Development launcher started Vite and backend. HTTP checks passed TSX
  compilation, React dependencies, API proxy and WebSocket proxy.
- Launcher cleaned up backend on development-server startup failure; Uvicorn
  reported completed application shutdown. FastAPI lifespan/thread shutdown
  also tested in pytest. Server ports became available after stopping launchers.
- UI design source preflight: no hard violations or warnings.
- Coordinate review: NED X North/Y East; screen X East/Y negative North;
  yaw radians converted/normalized; RAD radians multiplied by meter distance
  once; range centimeters converted once; sensor corrections before yaw;
  origin reset has no flight-controller command; one outbound command type
  only (SET_MESSAGE_INTERVAL).

## Not verified

- Initial build had no COM ports. Follow-up verified live FC heartbeat and
  messages after hardware was connected. Physical-direction accuracy, complete
  movement paths, real USB loss/reconnect and calibration remain unverified.
- The computer-use environment exposed no browser. Browser visual inspection,
  button interaction, Canvas performance and live resize were not observed.
  API/proxy/simulation and build checks passed; these do not replace browser QA.
- Flight accuracy, heavily tilted terrain geometry and yaw alignment are not
  claimed. Flow integration is deliberately a debug estimate.

## Implementation limits

- Metric optical-flow integration defaults to ArduPilot OPTICAL_FLOW opt_m_x/y.
  RAD input is selectable; only one stream contributes displacement. Both need
  valid measured ground distance.
- Uses downward-facing DISTANCE_SENSOR only for range/fallback.
- Smoothing filters displayed velocity while preserving metric displacement.
- Live backend processing settings/origin are shared across tabs; map history,
  pause and clear are local to each browser.
