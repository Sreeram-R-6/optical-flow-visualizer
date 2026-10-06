# Validation evidence

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
