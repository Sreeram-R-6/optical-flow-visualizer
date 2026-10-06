import asyncio
from fastapi import WebSocket
from .config import SNAPSHOT_HZ
from .telemetry import TelemetryState

class WebSocketManager:
    def __init__(self, state: TelemetryState) -> None:
        self.state = state
        self.clients: set[WebSocket] = set()

    async def broadcast(self) -> None:
        while True:
            self.state.report_stale()
            snapshot = self.state.snapshot()
            async def send(client: WebSocket) -> None:
                try:
                    await asyncio.wait_for(client.send_json(snapshot), timeout=0.25)
                except Exception:
                    self.clients.discard(client)
                    try:
                        await client.close()
                    except Exception:
                        pass
            await asyncio.gather(*(send(c) for c in tuple(self.clients)))
            await asyncio.sleep(1 / SNAPSHOT_HZ)

    async def close(self) -> None:
        for client in tuple(self.clients):
            try:
                await client.close(code=1001)
            except Exception:
                pass
        self.clients.clear()
