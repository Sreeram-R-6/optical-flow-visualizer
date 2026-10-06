from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class ConnectRequest(BaseModel):
    port: str = Field(pattern=r"(?i)^COM[1-9][0-9]*$")
    baud: Literal[57600, 115200, 230400, 460800, 921600] = 115200

class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["optical_flow", "local_position"] = "optical_flow"
    flow_input: Literal["mission_planner", "rad"] = "mission_planner"
    swap_xy: bool = False
    invert_x: bool = False
    invert_y: bool = False
    rotation: Literal[0, 90, 180, 270] = 0
    smoothing: Literal["OFF", "LOW", "MEDIUM"] = "LOW"
    deadband: bool = False
    deadband_rad: float = Field(default=0.0002, ge=0, le=0.05)
    yaw_compensation: bool = True
    gyro_compensation: bool = True

class SimulationInput(BaseModel):
    mode: Literal["auto", "manual"] = "auto"
    north: float = Field(default=0, ge=-1, le=1)
    east: float = Field(default=0, ge=-1, le=1)
