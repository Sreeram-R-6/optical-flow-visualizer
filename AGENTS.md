# Project conventions

This is a localhost read-only telemetry visualizer. Never add vehicle-control commands.
The only outbound MAVLink command allowed is MAV_CMD_SET_MESSAGE_INTERVAL.
All sensor transforms belong in backend/flow_processor.py. NED X is North;
NED Y is East. Browser map X is East and screen Y decreases with North.
Keep simulation isolated from serial. No automatic serial reconnect on browser load.
Use Context7 resolve-library-id followed by query-docs for library-specific APIs.
Run `.venv\Scripts\python -m pytest -q`, then frontend `npm run typecheck`,
`npm test`, and `npm run build` after material changes.
