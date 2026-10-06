import base64
import pytest
from fastapi.testclient import TestClient
from pymavlink.dialects.v20 import ardupilotmega as mav
from backend.cloud import app


def frame(message, timestamp, v1=False, system=1, component=1):
    encoder = mav.MAVLink(None, srcSystem=system, srcComponent=component)
    return {'data': base64.b64encode(message.pack(encoder, force_mavlink1=v1)).decode(), 'time': timestamp}


def heartbeat(timestamp=0, **kwargs):
    return frame(mav.MAVLink_heartbeat_message(2, 3, 0, 0, 4, 3), timestamp, **kwargs)


def send(frames=None, now=0.2, session=None, settings=None, **kwargs):
    body = {'frames': frames or [], 'now': now, 'settings': settings or {}, **kwargs}
    if session is not None:
        body['session'] = session
    response = TestClient(app).post('/api/usb/step', json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('v1', [False, True])
def test_usb_decodes_real_frames_and_only_requests_message_intervals(v1):
    frames = [heartbeat(v1=v1),
        frame(mav.MAVLink_attitude_message(1000, 0, 0, 0, 0, 0, 0), .1, v1=v1),
        frame(mav.MAVLink_distance_sensor_message(1000, 10, 500, 150, 0, 0, 25, 0), .1, v1=v1),
        frame(mav.MAVLink_optical_flow_rad_message(1_700_000_000_000_000, 0, 100000, -.01, .02, 0, 0, 0, 2400, 220, 0, 1.5), .1, v1=v1)]
    packet = send(frames, settings={'flow_input': 'rad'})
    assert packet['telemetry']['connected']
    assert not packet['telemetry']['simulation']
    assert packet['telemetry']['port'] == 'Browser USB'
    assert packet['telemetry']['position']['north'] == pytest.approx(.03)
    assert packet['telemetry']['position']['east'] == pytest.approx(.015)
    assert len(packet['outgoing']) == 6
    for encoded in packet['outgoing']:
        command = mav.MAVLink(None).decode(bytearray(base64.b64decode(encoded)))
        assert command.get_type() == 'COMMAND_LONG'
        assert command.command == mav.MAV_CMD_SET_MESSAGE_INTERVAL
        assert command.target_system == command.target_component == 1
    resumed = send([heartbeat(.3, v1=v1)], now=.4, session=packet['session'], settings={'flow_input': 'rad'})
    assert resumed['outgoing'] == []
    assert resumed['telemetry']['position']['north'] == pytest.approx(.03)


def test_usb_legacy_flow_and_restored_rate_baseline():
    common = [heartbeat(), frame(mav.MAVLink_attitude_message(0, 0, 0, 0, 0, 0, 0), .1),
              frame(mav.MAVLink_distance_sensor_message(0, 10, 500, 150, 0, 0, 25, 0), .1)]
    first = send(common + [frame(mav.MAVLink_optical_flow_message(100, 0, 0, 0, 0, .2, 220, 999), .1)])
    second = send([frame(mav.MAVLink_optical_flow_message(200, 0, 0, 0, 0, .2, 220, 999), .2)],
                  now=.2, session=first['session'])
    assert second['telemetry']['position']['available']
    assert second['telemetry']['position']['north'] == pytest.approx(.03)
    assert second['telemetry']['flow']['distance_source'] == 'DISTANCE_SENSOR'
    duplicate = send([frame(mav.MAVLink_optical_flow_message(200, 0, 0, 0, 0, .2, 220, 999), .3)],
                     now=.3, session=second['session'])
    assert duplicate['telemetry']['position']['north'] == pytest.approx(.03)


def test_usb_crc_filtering_vehicle_filter_and_timeout():
    damaged = bytearray(base64.b64decode(heartbeat()['data']))
    damaged[-1] ^= 1
    corrupt = {'data': base64.b64encode(damaged).decode(), 'time': 0}
    gcs = frame(mav.MAVLink_heartbeat_message(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 4, 3), 0, system=255)
    waiting = send([corrupt, gcs])
    assert waiting['telemetry']['state'] == 'WAITING_FOR_HEARTBEAT'
    assert waiting['telemetry']['invalid_packets'] == 1
    assert waiting['outgoing'] == []
    timeout = send(now=12.1, session=waiting['session'])
    assert timeout['telemetry']['state'] == 'ERROR'
    active = send([heartbeat()])
    lost = send(now=5.1, session=active['session'])
    assert lost['telemetry']['state'] == 'CONNECTION_LOST'
    assert not lost['telemetry']['connected']
    unplugged = send(now=.3, session=active['session'], open=False, error='USB unplugged')
    assert unplugged['telemetry']['error'] == 'USB unplugged'
    assert not unplugged['telemetry']['simulation']
    other_vehicle = send([heartbeat(.3, system=2)], now=.4, session=active['session'])
    assert other_vehicle['session']['times']['HEARTBEAT'] == 0


def test_usb_origin_and_settings_survive_stateless_requests():
    packet = send([heartbeat(), frame(mav.MAVLink_local_position_ned_message(0, 2, 3, -1, 0, 0, 0), .1)],
                  settings={'source': 'local_position'})
    moved = send([frame(mav.MAVLink_local_position_ned_message(0, 4, 6, -1, 0, 0, 0), .2)],
                 now=.2, session=packet['session'], settings={'source': 'local_position'})
    assert moved['telemetry']['position']['north'] == 2
    assert moved['telemetry']['position']['east'] == 3
    reset = send(now=.3, session=moved['session'], settings={'source': 'local_position'}, reset_origin=True)
    assert reset['telemetry']['position']['north'] == reset['telemetry']['position']['east'] == 0
    assert reset['telemetry']['revision'] > moved['telemetry']['revision']
    independent = send()
    assert not independent['telemetry']['connected']
    assert not independent['telemetry']['simulation']


def test_usb_rejects_unbounded_or_future_input():
    client = TestClient(app)
    assert client.post('/api/usb/step', json={'now': 0, 'settings': {}, 'frames': [heartbeat(10)]}).status_code == 422
    assert client.post('/api/usb/step', json={'now': 0, 'settings': {}, 'frames': [heartbeat()] * 129}).status_code == 422
