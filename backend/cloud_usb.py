"""Browser USB byte decoding with caller-owned state; never opens a server port."""
import base64
import binascii
from collections import deque
from typing import Annotated, Literal
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat
from pymavlink.dialects.v20 import ardupilotmega as mav
from .config import CONNECT_TIMEOUT, HEARTBEAT_TIMEOUT, MESSAGE_RATES
from .models import Settings
from .telemetry import MESSAGE_TYPES, TelemetryState, clean

router = APIRouter()
Number = Annotated[FiniteFloat, Field(ge=-1e12, le=1e12)]
Clock = Annotated[FiniteFloat, Field(ge=0, le=1e12)]
Kind = Literal['HEARTBEAT', 'OPTICAL_FLOW_RAD', 'OPTICAL_FLOW', 'DISTANCE_SENSOR',
               'LOCAL_POSITION_NED', 'ATTITUDE', 'SYS_STATUS']


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class FlowMemory(MemoryModel):
    north: Number = 0
    east: Number = 0
    velocity: tuple[Number, Number] | None = None
    last_stamp: tuple[int, int] | None = None
    rate_time: Clock | None = None
    rate_stamp: tuple[int, int] | None = None


class Event(MemoryModel):
    timestamp: Clock
    message: str = Field(max_length=256)
    level: str = Field(max_length=16)


class UsbSession(MemoryModel):
    settings: Settings = Field(default_factory=Settings)
    processor: FlowMemory = Field(default_factory=FlowMemory)
    raw: dict[Kind, dict[str, int | FiniteFloat | None]] = Field(default_factory=dict)
    times: dict[Kind, Clock] = Field(default_factory=dict)
    rates: dict[Kind, list[Clock]] = Field(default_factory=dict)
    origin: tuple[Number, Number] | None = None
    flow_valid: bool = False
    flow_distance: Number | None = None
    flow_distance_source: Kind | None = None
    range_distance: Number | None = None
    range_time: Clock | None = None
    invalid_packets: int = Field(default=0, ge=0, le=1_000_000_000)
    revision: int = Field(default=0, ge=0, le=1_000_000_000)
    target: tuple[Annotated[int, Field(ge=1, le=255)], Annotated[int, Field(ge=0, le=255)]] | None = None
    requests_sent: bool = False
    state: Literal['WAITING_FOR_HEARTBEAT', 'CONNECTED', 'CONNECTION_LOST', 'ERROR'] = 'WAITING_FOR_HEARTBEAT'
    events: list[Event] = Field(default_factory=list, max_length=100)


class UsbFrame(MemoryModel):
    data: str = Field(max_length=400)
    time: Clock


class UsbStep(MemoryModel):
    session: UsbSession = Field(default_factory=UsbSession)
    frames: list[UsbFrame] = Field(default_factory=list, max_length=128)
    now: Clock
    settings: Settings
    reset_origin: bool = False
    open: bool = True
    error: str | None = Field(default=None, max_length=256)
    baud: Literal[57600, 115200, 230400, 460800, 921600] = 115200


def restore(session: UsbSession) -> TelemetryState:
    state = TelemetryState()
    state.events = deque((e.model_dump() for e in session.events), maxlen=100)
    state.settings = session.settings
    for key in ('raw', 'times', 'origin', 'flow_valid', 'flow_distance', 'flow_distance_source',
                'range_distance', 'range_time', 'invalid_packets', 'revision', 'state'):
        setattr(state, key, getattr(session, key))
    state.rates = {k: deque(session.rates.get(k, [])[-100:], maxlen=100) for k in MESSAGE_TYPES}
    for key, value in session.processor.model_dump().items():
        setattr(state.processor, key, value)
    state.system_id = session.target[0] if session.target else None
    state.port = 'Browser USB'
    return state


@router.post('/api/usb/step')
def usb_step(body: UsbStep, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    # Limit caller-owned state as well as new bytes; no hidden per-instance sessions.
    if any(len(raw) > 50 for raw in body.session.raw.values()) or any(len(rates) > 100 for rates in body.session.rates.values()):
        raise HTTPException(422, 'USB state exceeds bounds')
    if any(frame.time > body.now for frame in body.frames) or any(t > body.now for t in body.session.times.values()):
        raise HTTPException(422, 'USB timestamps must not be in the future')
    state = restore(body.session)
    state.baud = body.baud
    state.update_settings(body.settings)
    if body.reset_origin:
        state.reset_origin()
    target, requested = body.session.target, body.session.requests_sent
    outgoing = []
    if body.open:
        for frame in body.frames:
            try:
                data = base64.b64decode(frame.data, validate=True)
                if not 8 <= len(data) <= 280:
                    raise ValueError('Invalid frame size')
                message = mav.MAVLink(None).decode(bytearray(data))
            except (ValueError, binascii.Error, mav.MAVError):
                state.invalid_packets += 1
                continue
            kind = message.get_type()
            if kind == 'HEARTBEAT' and target is None:
                if message.autopilot == mav.MAV_AUTOPILOT_INVALID or message.type == mav.MAV_TYPE_GCS or message.get_srcSystem() == 0:
                    continue
                target = (message.get_srcSystem(), message.get_srcComponent())
                state.system_id = target[0]
                state.event(f'MAVLink heartbeat received; browser USB vehicle {target[0]}')
            if not target or message.get_srcSystem() != target[0]:
                continue
            if kind == 'HEARTBEAT' and message.get_srcComponent() != target[1]:
                continue
            if kind in MESSAGE_TYPES:
                raw = clean(message.to_dict())
                raw.pop('mavpackettype', None)
                # Every supported telemetry message has scalar numeric fields.
                raw = {k: v for k, v in raw.items() if isinstance(v, (int, float)) or v is None}
                state.ingest(kind, raw, frame.time)
            if kind == 'HEARTBEAT' and not requested:
                encoder = mav.MAVLink(None, srcSystem=255, srcComponent=190)
                for name, hz in MESSAGE_RATES.items():
                    # The ONLY outbound command; cannot arm or control the vehicle.
                    command = encoder.command_long_encode(*target, mav.MAV_CMD_SET_MESSAGE_INTERVAL,
                        0, getattr(mav, f'MAVLINK_MSG_ID_{name}'), 1_000_000 / hz, 0, 0, 0, 0, 0)
                    outgoing.append(base64.b64encode(command.pack(encoder, force_mavlink1=data[0] == 254)).decode())
                    encoder.seq += 1
                requested = True
            if kind == 'COMMAND_ACK' and message.command == mav.MAV_CMD_SET_MESSAGE_INTERVAL and message.result != 0:
                state.event(f'Message interval request result {message.result}; listening to existing streams', 'WARNING')
    heartbeat = state.times.get('HEARTBEAT')
    if not body.open:
        state.transition('CONNECTION_LOST' if target else 'ERROR', body.error or 'USB connection closed. Connect explicitly to retry.')
    elif heartbeat is None and body.now > CONNECT_TIMEOUT:
        state.transition('ERROR', 'No vehicle HEARTBEAT in 12 seconds. Check baud and MAVLink configuration.')
    elif heartbeat is not None and body.now - heartbeat > HEARTBEAT_TIMEOUT:
        state.transition('CONNECTION_LOST', 'MAVLink heartbeat lost. Connect explicitly to retry.')
    stored = {k: getattr(state, k) for k in ('raw', 'times', 'origin', 'flow_valid', 'flow_distance',
        'flow_distance_source', 'range_distance', 'range_time', 'invalid_packets', 'revision', 'state')}
    stored.update(settings=state.settings.model_dump(), processor={k: getattr(state.processor, k) for k in FlowMemory.model_fields},
        rates={k: list(v) for k, v in state.rates.items()}, target=target, requests_sent=requested, events=list(state.events))
    snapshot = state.snapshot(now=body.now)
    snapshot['mode'] = 'hosted_demo'
    return {'session': UsbSession.model_validate(stored).model_dump(), 'telemetry': snapshot, 'outgoing': outgoing}
