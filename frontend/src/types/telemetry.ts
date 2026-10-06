export interface Settings {
  source: 'optical_flow' | 'local_position'; swap_xy: boolean; invert_x: boolean; invert_y: boolean;
  flow_input: 'mission_planner'|'rad';
  rotation: 0 | 90 | 180 | 270; smoothing: 'OFF' | 'LOW' | 'MEDIUM'; deadband: boolean;
  deadband_rad: number; yaw_compensation: boolean; gyro_compensation: boolean;
}
export const defaultSettings: Settings = {source:'optical_flow',flow_input:'mission_planner',swap_xy:false,invert_x:false,invert_y:false,rotation:0,smoothing:'LOW',deadband:false,deadband_rad:0.0002,yaw_compensation:true,gyro_compensation:true};
export type ConnectionState = 'DISCONNECTED'|'CONNECTING'|'WAITING_FOR_HEARTBEAT'|'CONNECTED'|'CONNECTION_LOST'|'ERROR';
export interface Telemetry {
  mode?: 'hosted_demo';
  timestamp:number; state:ConnectionState; connected:boolean; heartbeat:boolean; heartbeat_age_ms:number|null;
  simulation:boolean; port:string|null; baud:number; error:string|null; system_id:number|null; revision:number;
  position:{source:Settings['source'];available:boolean;reason:string|null;x:number|null;y:number|null;north:number|null;east:number|null;distance:number|null};
  flow:{status:string;age_ms:number|null;rate_hz:number;input_message:string;opt_m_x:number|null;opt_m_y:number|null;opt_status:string;integrated_x?:number|null;integrated_y?:number|null;quality?:number|null;distance?:number|null;ground_distance:number|null;distance_source:string|null;[key:string]:unknown};
  legacy_flow:Record<string,unknown>|null;
  rangefinder:{distance:number|null;status:string};
  attitude:{roll:number|null;pitch:number|null;yaw:number|null;status:string};
  velocity:{vx:number|null;vy:number|null;speed:number|null};
  debug:Record<string,{age_ms:number|null;rate_hz:number;last_timestamp:number|null}>;
  invalid_packets:number; settings:Settings;events:{timestamp:number;message:string;level:string}[];
}
export interface TrailPoint {x:number;y:number;timestamp:number;quality?:number}
export interface MapPreferences {scale:string;showTrail:boolean;boundary:boolean;width:number;height:number}
