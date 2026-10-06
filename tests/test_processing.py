import math
import pytest
from backend.flow_processor import FlowProcessor, body_to_world, ned_position, sensor_transform
from backend.models import Settings
from backend.telemetry import TelemetryState, data_status

def flow(**changes):
    return {"integrated_x": -0.01, "integrated_y": 0.02, "integrated_xgyro": 0, "integrated_ygyro": 0,
            "quality": 220, "time_usec": 100, "sensor_id": 0, "integration_time_us": 100000, **changes}

def test_ned_and_distance():
    p = ned_position(4, 6, (1, 2))
    assert p == {"north": 3, "east": 4, "x": 4, "y": 3, "distance": 5}

def test_flow_geometry_and_interval():
    p = FlowProcessor()
    assert p.integrate(flow(), 2, 0, Settings())
    assert p.north == pytest.approx(0.04)
    assert p.east == pytest.approx(0.02)
    assert p.velocity == pytest.approx((0.4, 0.2))
    assert not p.integrate(flow(), 2, 0, Settings())
    assert p.north == pytest.approx(0.04)

@pytest.mark.parametrize('distance', [None, -1, 0, float('nan'), float('inf')])
def test_invalid_distance(distance):
    p = FlowProcessor()
    assert not p.integrate(flow(), distance, 0, Settings())
    assert p.north == p.east == 0

def test_gyro_compensation():
    p = FlowProcessor()
    assert p.integrate(flow(integrated_xgyro=-0.01, integrated_ygyro=0.02), 2, 0, Settings())
    assert p.north == p.east == 0

def test_axis_swap_inversion():
    assert sensor_transform(1, 2, Settings(swap_xy=True)) == pytest.approx((2, 1))
    assert sensor_transform(1, 2, Settings(invert_x=True)) == pytest.approx((-1, 2))
    assert sensor_transform(1, 2, Settings(invert_y=True)) == pytest.approx((1, -2))

@pytest.mark.parametrize('rotation,expected', [(0,(1,2)),(90,(-2,1)),(180,(-1,-2)),(270,(2,-1))])
def test_rotation(rotation, expected):
    assert sensor_transform(1, 2, Settings(rotation=rotation)) == pytest.approx(expected)

def test_yaw():
    assert body_to_world(1, 0, math.pi/2) == pytest.approx((0, 1))
    assert body_to_world(0, 1, math.pi/2) == pytest.approx((-1, 0))

def test_origin_reset():
    s = TelemetryState()
    s.ingest('LOCAL_POSITION_NED', {'x': 12, 'y': -3}, 10)
    s.processor.north, s.processor.east = 5, 6
    s.reset_origin()
    assert s.origin == (12, -3)
    assert s.processor.north == s.processor.east == 0
    s.update_settings(Settings(source='local_position'))
    s.ingest('HEARTBEAT', {}, 10)
    s.ingest('LOCAL_POSITION_NED', {'x': 13, 'y': -1, 'vx': 3, 'vy': 4}, 10)
    p = s.snapshot(10)['position']
    assert p['north'] == 1 and p['east'] == 2
    assert s.snapshot(10)['velocity']['speed'] == 5

def test_stale_telemetry():
    assert data_status(None, 10) == 'NO DATA'
    assert data_status(9.5, 10) == 'ACTIVE'
    assert data_status(8, 10) == 'STALE'
    s = TelemetryState()
    s.ingest('HEARTBEAT', {}, 10)
    assert s.snapshot(10)['heartbeat']
    assert not s.snapshot(16)['heartbeat']

def test_rangefinder_units_and_fallback():
    s = TelemetryState()
    s.update_settings(Settings(flow_input='rad'))
    s.ingest('HEARTBEAT', {}, 10)
    s.ingest('ATTITUDE', {'yaw':0,'roll':0,'pitch':0}, 10)
    s.ingest('DISTANCE_SENSOR', {'orientation':25,'current_distance':200,'min_distance':10,'max_distance':500}, 10)
    s.ingest('OPTICAL_FLOW_RAD', flow(distance=-1), 10)
    assert s.snapshot(10)['rangefinder']['distance'] == 2
    assert s.snapshot(10)['position']['north'] == pytest.approx(.04)
    assert s.snapshot(10)['flow']['ground_distance'] == 2
    assert s.snapshot(10)['flow']['distance_source'] == 'DISTANCE_SENSOR'
    s.ingest('OPTICAL_FLOW_RAD', flow(time_usec=200,distance=-1), 12)
    assert not s.snapshot(12)['position']['available']

def test_side_rangefinder_not_ground_distance():
    s = TelemetryState()
    s.ingest('DISTANCE_SENSOR', {'orientation':0,'current_distance':200,'min_distance':10,'max_distance':500}, 10)
    assert s.snapshot(10)['rangefinder']['distance'] is None

def test_yaw_degrees_and_invalid_packets():
    s = TelemetryState()
    s.ingest('ATTITUDE', {'yaw':-math.pi/2,'roll':math.pi/180,'pitch':float('nan')}, 10)
    assert s.snapshot(10)['attitude']['yaw'] == 270
    assert s.snapshot(10)['attitude']['roll'] == pytest.approx(1)
    assert s.snapshot(10)['attitude']['pitch'] is None

def test_transform_before_yaw():
    p = FlowProcessor()
    p.integrate(flow(integrated_x=0, integrated_y=.02), 2, math.pi/2, Settings(rotation=90))
    assert p.north == pytest.approx(-.04)
    assert p.east == pytest.approx(0)

def test_quality_interval_jump_rejection():
    for raw in [flow(quality=0), flow(integration_time_us=0), flow(integrated_x=2), flow(integrated_y=float('nan'))]:
        assert not FlowProcessor().integrate(raw, 2, 0, Settings())

def test_smoothing_preserves_distance():
    p = FlowProcessor()
    p.integrate(flow(), 2, 0, Settings(smoothing='MEDIUM'))
    p.integrate(flow(time_usec=200, integrated_y=.04, integration_time_us=200000), 2, 0, Settings(smoothing='MEDIUM'))
    assert p.north == pytest.approx(.12)

def legacy_flow(**changes):
    return {'time_usec':1000,'sensor_id':0,'flow_comp_m_x':-.1,'flow_comp_m_y':.2,
            'quality':220,'ground_distance':2,**changes}

def test_mission_planner_rates_distance_time_and_no_double_gyro():
    p = FlowProcessor()
    settings = Settings()
    assert not p.integrate_rates(legacy_flow(),10,2,0,settings)
    assert p.integrate_rates(legacy_flow(time_usec=1100),10.1,2,0,settings)
    assert p.north == pytest.approx(.04)
    assert p.east == pytest.approx(.02)
    assert p.velocity == pytest.approx((.4,.2))
    assert not p.integrate_rates(legacy_flow(time_usec=1100),10.2,2,0,settings)
    assert p.north == pytest.approx(.04)
    assert not p.integrate_rates(legacy_flow(time_usec=2000),12,2,0,settings)
    assert p.north == pytest.approx(.04)

def test_mission_planner_fields_and_stream_selection():
    s = TelemetryState()
    s.ingest('HEARTBEAT',{},10)
    s.ingest('ATTITUDE',{'yaw':0,'roll':0,'pitch':0},10)
    s.ingest('DISTANCE_SENSOR',{'orientation':25,'current_distance':200,'min_distance':10,'max_distance':500},10)
    s.ingest('OPTICAL_FLOW',legacy_flow(),10)
    s.ingest('OPTICAL_FLOW',legacy_flow(time_usec=1100),10.1)
    before=s.snapshot(10.1)['position']['north']
    s.ingest('OPTICAL_FLOW_RAD',flow(distance=2),10.1)
    packet=s.snapshot(10.1)
    assert packet['position']['north'] == before == pytest.approx(.04)
    assert packet['flow']['opt_m_x'] == -.1
    assert packet['flow']['opt_m_y'] == .2
    assert packet['flow']['input_message'] == 'OPTICAL_FLOW'
    assert packet['flow']['distance_source'] == 'DISTANCE_SENSOR'
    assert packet['flow']['status'] == 'ACTIVE'
    assert s.snapshot(12)['flow']['status'] == 'STALE'

def test_mission_planner_missing_distance_does_not_integrate():
    p=FlowProcessor()
    assert not p.integrate_rates(legacy_flow(),10,None,0,Settings())
    assert not p.integrate_rates(legacy_flow(time_usec=1100),10.1,None,0,Settings())
    assert p.north == p.east == 0
