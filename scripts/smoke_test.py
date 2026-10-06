"""Live acceptance smoke check. Run with server on 8000, no real FC connected.
Starts/stops simulation and changes local settings; never connects serial.
"""
import asyncio
import json
import math
import re
import httpx
from websockets.asyncio.client import connect

async def main() -> None:
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000') as client:
        initial = (await client.get('/api/status')).json()
        if initial['state'] not in ('DISCONNECTED', 'ERROR', 'CONNECTION_LOST'):
            raise RuntimeError('Disconnect vehicle/simulation before running this check.')
        original = initial['settings']
        page = await client.get('/')
        assert page.status_code == 200 and 'Optical Flow Visualizer' in page.text
        asset = re.search(r'src="([^"]+\.js)"',page.text)
        assert asset and (await client.get(asset[1])).status_code == 200
        assert isinstance((await client.get('/api/ports')).json(), list)
        try:
            assert (await client.post('/api/simulation/start')).status_code == 200
            await asyncio.sleep(.2)
            async with connect('ws://127.0.0.1:8000/ws/telemetry',origin='http://127.0.0.1:8000') as ws:
                first = json.loads(await ws.recv())
                await asyncio.sleep(.4)
                # Read until a current snapshot, discarding buffered older frames.
                while True:
                    current = json.loads(await ws.recv())
                    if current['timestamp']-first['timestamp'] > .35:
                        break
                assert current['simulation'] and current['connected']
                assert current['position']['available']
                assert current['flow']['status'] == 'ACTIVE'
                assert current['rangefinder']['status'] == 'ACTIVE'
                assert current['position']['north'] != first['position']['north']
                assert math.isfinite(current['position']['distance'])
            await client.post('/api/simulation/input',json={'mode':'manual','north':0,'east':0})
            await client.post('/api/reset-origin')
            await asyncio.sleep(.1)
            p = (await client.get('/api/status')).json()['position']
            assert abs(p['north']) < .01 and abs(p['east']) < .01
            for axis in ('invert_x','invert_y','swap_xy'):
                settings = {**original,axis:True}
                assert (await client.post('/api/settings',json=settings)).status_code == 200
            for rotation in (90,180,270,0):
                assert (await client.post('/api/settings',json={**original,'rotation':rotation})).status_code == 200
            await client.post('/api/settings',json={**original,'source':'local_position'})
            assert (await client.get('/api/status')).json()['position']['source'] == 'local_position'
            await client.post('/api/simulation/input',json={'mode':'manual','north':1,'east':0})
            await asyncio.sleep(.2)
            assert (await client.get('/api/status')).json()['velocity']['vx'] > 0
            print('PASS: built frontend/assets, ports API, live WebSocket movement, range, reset, axes, source and manual simulation')
        finally:
            await client.post('/api/disconnect')
            await client.post('/api/settings',json=original)
        assert not (await client.get('/api/status')).json()['connected']
        print('PASS: simulation stopped, backend remains healthy, original settings restored')

if __name__ == '__main__':
    asyncio.run(main())
