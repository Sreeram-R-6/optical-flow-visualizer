import time
import pytest
from unittest.mock import Mock
from pymavlink import mavutil
from backend.mavlink_connection import MAVLinkConnection
from backend.telemetry import TelemetryState
from backend.models import Settings

def wait_for(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    assert predicate()

def test_real_mavlink_decoding_thread_and_requests(monkeypatch):
    # Actual pymavlink v2 encoder/decoder, fake serial transport.
    from pymavlink.dialects.v20 import ardupilotmega as dialect
    encoder = dialect.MAVLink(None, srcSystem=1, srcComponent=1)
    messages = [
        dialect.MAVLink_heartbeat_message(2,3,0,0,4,3),
        dialect.MAVLink_attitude_message(1000,0,0,0,0,0,0),
        dialect.MAVLink_distance_sensor_message(1000,10,500,150,0,0,25,0),
        dialect.MAVLink_optical_flow_rad_message(1000000,0,100000,-.01,.02,0,0,0,2400,220,0,1.5),
        dialect.MAVLink_local_position_ned_message(1000,2,3,-1.5,.1,.2,0),
    ]
    decoder = dialect.MAVLink(None)
    packets = [decoder.parse_char(msg.pack(encoder)) for msg in messages]
    link = Mock()
    link.recv_match.side_effect = lambda **kwargs: packets.pop(0) if packets else None
    monkeypatch.setattr(mavutil,'mavlink_connection',lambda *a,**kw:link)
    state = TelemetryState()
    state.update_settings(Settings(flow_input='rad'))
    reader = MAVLinkConnection(state)
    reader.connect('COM10')
    wait_for(lambda: state.snapshot()['position']['available'])
    packet = state.snapshot()
    assert packet['position']['north'] == pytest.approx(.03)
    assert packet['position']['east'] == pytest.approx(.015)
    assert packet['rangefinder']['distance'] == 1.5
    assert packet['system_id'] == 1
    assert link.mav.command_long_send.call_count == 6
    for call in link.mav.command_long_send.call_args_list:
        assert call.args[2] == mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL
    state.update_settings(Settings(source='local_position'))
    assert state.snapshot()['connected']
    reader.disconnect()
    link.close.assert_called_once()
    assert reader.worker is None

def test_port_busy_does_not_crash(monkeypatch):
    def fail(*args,**kwargs):
        raise PermissionError('Access denied: port busy')
    monkeypatch.setattr(mavutil,'mavlink_connection',fail)
    state = TelemetryState()
    reader = MAVLinkConnection(state)
    reader.connect('COM3')
    wait_for(lambda:state.state=='ERROR')
    assert 'Access denied' in state.error
    reader.disconnect()

def test_unplug_and_reconnect(monkeypatch):
    from pymavlink.dialects.v20 import ardupilotmega as dialect
    heartbeat = dialect.MAVLink_heartbeat_message(2,3,0,0,4,3)
    heartbeat._header.srcSystem = heartbeat._header.srcComponent = 1
    link = Mock()
    link.recv_match.side_effect = [heartbeat, OSError('USB disconnected')]
    monkeypatch.setattr(mavutil,'mavlink_connection',lambda *a,**kw:link)
    state = TelemetryState()
    reader = MAVLinkConnection(state)
    reader.connect('COM3')
    wait_for(lambda:state.state=='CONNECTION_LOST')
    assert not state.snapshot()['connected']
    link.close.assert_called_once()
    reader.connect(None,simulation=True)
    wait_for(lambda:state.snapshot()['connected'])
    reader.disconnect()

def test_heartbeat_timeout(monkeypatch):
    import backend.mavlink_connection as module
    monkeypatch.setattr(module,'CONNECT_TIMEOUT',.05)
    link = Mock()
    link.recv_match.return_value = None
    monkeypatch.setattr(mavutil,'mavlink_connection',lambda *a,**kw:link)
    state = TelemetryState()
    reader = MAVLinkConnection(state)
    reader.connect('COM3')
    wait_for(lambda:state.state=='ERROR')
    assert 'HEARTBEAT' in state.error
    reader.disconnect()
    link.close.assert_called_once()
