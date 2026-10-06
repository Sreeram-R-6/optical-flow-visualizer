"""Verify the Vite development server compiles modules and proxies telemetry."""
import asyncio
import json
import re
import httpx
from websockets.asyncio.client import connect

async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:5173') as client:
        for path in ['/', '/api/health', '/src/main.tsx', '/src/App.tsx', '/src/components/DroneMap.tsx']:
            response = await client.get(path)
            assert response.status_code == 200, (path, response.text[:500])
        source = (await client.get('/src/main.tsx')).text
        for path in re.findall(r'from [\"\x27]([^\"\x27]+)', source):
            if path.startswith('/'):
                response = await client.get(path)
                assert response.status_code == 200, (path,response.text[:500])
                assert 'javascript' in response.headers.get('content-type',''), path
        assert (await client.get('/api/health')).json()['ok']
    async with connect('ws://127.0.0.1:5173/ws/telemetry',origin='http://127.0.0.1:5173') as ws:
        assert json.loads(await ws.recv())['state'] == 'DISCONNECTED'
    print('PASS: Vite page, TSX compilation, React dependencies, HTTP and WebSocket proxies')

if __name__=='__main__':
    asyncio.run(main())
