import axios from 'axios'
import type { Pose, RobotState } from '@/stores/robot'
import type { VisualizationConfig } from '@/stores/visualization'
import { decodeMapSnapshot, type MapWireSnapshot } from '@/mapTransport'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 5000,
  withCredentials: true,
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = String(error?.config?.url || '')
    if (error?.response?.status === 401 && !url.startsWith('/auth/')) {
      window.dispatchEvent(new CustomEvent('webrobot:session-expired'))
    }
    return Promise.reject(error)
  },
)

export interface CommandResponse { success: boolean; state: RobotState }
export interface ArmConfig {
  enabled: boolean
  motion_commands_enabled: boolean
  model: string
  transport: 'direct' | 'industrial_pc'
  host: string
  port: number
  network_interface: string
  expected_tool: string
  collision_level: number
  joint_speed_percent: number
  pose_speed_percent: number
  workspace_min_m: number[]
  workspace_max_m: number[]
  max_pose_segment_m: number
  keepout_enabled: boolean
  standby_joints_deg: number[]
  gripper_enabled: boolean
  gripper_commands_enabled: boolean
}
export type RuntimePhase = 'disabled' | 'unconfigured' | 'offline' | 'stopped' | 'starting' | 'running' | 'stopping' | 'error'
export interface RuntimeTaskState { id: string; label: string; state: 'pending' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error'; pid: number | null; message: string; dependencies: string[] }
export interface RuntimeStatus { agent_version: number; orchestrating: boolean; enabled: boolean; reachable: boolean; phase: RuntimePhase; host: string; message: string; supervisor_pid: number | null; tasks: RuntimeTaskState[]; updated_at: string; legacy_can0_active?: boolean }
export interface RuntimeActionResponse { success: boolean; status: RuntimeStatus }
export interface MapLibrary { maps: string[] }
export interface NavigationStatus { phase: 'idle' | 'sending' | 'navigating' | 'canceling' | 'succeeded' | 'canceled' | 'failed'; message: string; x: number | null; y: number | null; yaw: number | null }

export const robotApi = {
  status: () => api.get<RobotState>('/system/status').then((response) => response.data),
  moveChassis: (linear: number, angular: number) =>
    api.post<CommandResponse>('/chassis/move', { linear, angular }).then((response) => response.data),
  stopChassis: () => api.post<CommandResponse>('/chassis/stop', {}, { timeout: 10000 }).then((response) => response.data),
  armConfig: () => api.get<ArmConfig>('/arm/config').then((response) => response.data),
  connectArm: () => api.post<CommandResponse>('/arm/connect', {}, { timeout: 60000 }).then((response) => response.data),
  disconnectArm: () => api.post<CommandResponse>('/arm/disconnect', {}, { timeout: 12000 }).then((response) => response.data),
  moveJoint: (joint: number, position: number, speed = 5) =>
    api.post<CommandResponse>('/arm/joint', { joint, position, speed }, { timeout: 15000 }).then((response) => response.data),
  moveJoints: (positions: number[], speed = 5) =>
    api.post<CommandResponse>('/arm/joints', { positions, speed }, { timeout: 15000 }).then((response) => response.data),
  movePose: (pose: Pose, speed = 5) => api.post<CommandResponse>('/arm/pose', { ...pose, speed }, { timeout: 15000 }).then((response) => response.data),
  stopArm: () => api.post<CommandResponse>('/arm/stop', {}, { timeout: 10000 }).then((response) => response.data),
  emergencyStopManipulator: () => api.post<CommandResponse>('/arm/emergency-stop', {}, { timeout: 10000 }).then((response) => response.data),
  openGripper: () => api.post<CommandResponse>('/gripper/open', {}, { timeout: 20000 }).then((response) => response.data),
  closeGripper: () => api.post<CommandResponse>('/gripper/close', {}, { timeout: 20000 }).then((response) => response.data),
  stopGripper: () => api.post<CommandResponse>('/gripper/stop', {}, { timeout: 10000 }).then((response) => response.data),
  visualizationConfig: () => api.get<VisualizationConfig>('/visualization/config').then((response) => response.data),
  map: () => api.get<MapWireSnapshot>('/visualization/map').then((response) => decodeMapSnapshot(response.data)),
  clearMapCache: () => api.post<MapWireSnapshot>('/visualization/map/cache/clear').then((response) => decodeMapSnapshot(response.data)),
  navigationStatus: () => api.get<NavigationStatus>('/visualization/navigation/status').then((response) => response.data),
  navigateTo: (x: number, y: number, yaw: number, frame_id: string) =>
    api.post<NavigationStatus>('/visualization/navigation/goal', { x, y, yaw, frame_id }, { timeout: 15000 }).then((response) => response.data),
  cancelNavigation: () => api.post<NavigationStatus>('/visualization/navigation/cancel', {}, { timeout: 8000 }).then((response) => response.data),
  runtimeStatus: () => api.get<RuntimeStatus>('/runtime/status', { timeout: 10000 }).then((response) => response.data),
  startRuntime: () => api.post<RuntimeActionResponse>('/runtime/start', {}, { timeout: 25000 }).then((response) => response.data),
  stopRuntime: () => api.post<RuntimeActionResponse>('/runtime/stop', {}, { timeout: 25000 }).then((response) => response.data),
  startRuntimeTask: (taskId: string) => api.post<RuntimeActionResponse>(`/runtime/tasks/${taskId}/start`, {}, { timeout: 25000 }).then((response) => response.data),
  stopRuntimeTask: (taskId: string) => api.post<RuntimeActionResponse>(`/runtime/tasks/${taskId}/stop`, {}, { timeout: 25000 }).then((response) => response.data),
  runtimeLogs: () => api.get<{ lines: string[] }>('/runtime/logs', { params: { lines: 160 }, timeout: 12000 }).then((response) => response.data),
  startManualMapping: () => api.post<RuntimeActionResponse>('/runtime/mapping/manual/start', {}, { timeout: 30000 }).then((response) => response.data),
  startAutomaticMapping: () => api.post<RuntimeActionResponse>('/runtime/mapping/automatic/start', {}, { timeout: 30000 }).then((response) => response.data),
  stopMapping: () => api.post<RuntimeActionResponse>('/runtime/mapping/stop', {}, { timeout: 30000 }).then((response) => response.data),
  maps: () => api.get<MapLibrary>('/runtime/maps', { timeout: 12000 }).then((response) => response.data),
  saveMap: (name: string) => api.post<MapLibrary>('/runtime/maps/save', { name }, { timeout: 60000 }).then((response) => response.data),
  importMap: (name: string, yaml_base64: string, pgm_base64: string) => api.post<MapLibrary>('/runtime/maps/import', { name, yaml_base64, pgm_base64 }, { timeout: 60000 }).then((response) => response.data),
}
