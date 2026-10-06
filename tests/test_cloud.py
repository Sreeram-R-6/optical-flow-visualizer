from fastapi.testclient import TestClient
from backend.cloud import app


def test_cloud_session_is_stateless_and_preserves_north_east():
    client = TestClient(app)
    assert client.get('/api/health').json()['mode'] == 'hosted_demo'
    assert client.get('/api/ports').json() == []
    body = {'session': {'active': True, 'controls': {'mode': 'manual', 'north': 1, 'east': 0}}}
    first = client.post('/api/demo/step', json=body)
    assert first.status_code == 200
    packet = first.json()
    assert packet['telemetry']['simulation']
    assert packet['telemetry']['position']['available']
    assert packet['telemetry']['position']['y'] > 0
    assert abs(packet['telemetry']['position']['x']) < 1e-9
    second = client.post('/api/demo/step', json={'session': packet['session']}).json()
    assert second['telemetry']['position']['y'] > packet['telemetry']['position']['y']
    isolated = client.post('/api/demo/step', json={}).json()
    assert isolated['telemetry']['state'] == 'DISCONNECTED'
    assert not isolated['telemetry']['position']['available']
    assert client.post('/api/connect', json={'port': 'COM3'}).status_code == 404


def test_cloud_rad_east_and_settings_transform():
    client = TestClient(app)
    session = {'active': True, 'controls': {'mode': 'manual', 'north': 0, 'east': 1},
               'settings': {'flow_input': 'rad'}}
    packet = client.post('/api/demo/step', json={'session': session}).json()
    assert packet['telemetry']['position']['x'] > 0
    assert abs(packet['telemetry']['position']['y']) < 1e-9
    session['settings']['invert_x'] = True
    inverted = client.post('/api/demo/step', json={'session': session}).json()
    assert inverted['telemetry']['position']['x'] < 0
    assert client.post('/api/demo/step', json={'dt': 999}).status_code == 422
