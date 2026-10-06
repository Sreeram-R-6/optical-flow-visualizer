import time
from fastapi.testclient import TestClient
from backend.main import app, state

def test_simulation_websocket_reset_and_shutdown():
    with TestClient(app) as client:
        assert client.get('/api/health').json()['read_only']
        assert isinstance(client.get('/api/ports').json(), list)
        assert client.post('/api/connect', json={'port':'udp:127.0.0.1','baud':115200}).status_code == 422
        assert client.post('/api/simulation/input', json={'mode':'manual'}).status_code == 409
        assert client.post('/api/simulation/start').status_code == 200
        time.sleep(.2)
        with client.websocket_connect('/ws/telemetry') as ws:
            packet = ws.receive_json()
            assert packet['simulation'] and packet['connected'] and packet['position']['available']
        assert client.post('/api/simulation/input', json={'mode':'manual','north':1,'east':0}).status_code == 200
        time.sleep(.2)
        assert client.post('/api/reset-origin').status_code == 200
        packet = client.get('/api/status').json()
        assert packet['connected']
        assert abs(packet['position']['north']) < .1
        assert client.post('/api/settings',json={'source':'local_position'}).status_code == 200
        assert client.post('/api/disconnect').json()['state'] == 'DISCONNECTED'
    assert not state.simulation

def test_origin_protection():
    with TestClient(app) as client:
        assert client.post('/api/simulation/start',headers={'Origin':'https://example.com'}).status_code == 403
