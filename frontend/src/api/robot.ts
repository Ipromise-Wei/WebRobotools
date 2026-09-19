import axios from 'axios'
import type { Pose, RobotState } from '@/stores/robot'
import type { MapSnapshot, VisualizationConfig } from '@/stores/visualization'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', timeout: 5000 })

export interface CommandResponse { success: boolean; state: RobotState }
export type RuntimePhase = 'disabled' | 'unconfigured' | 'offline' | 'stopped' | 'starting' | 'running' | 'stopping' | 'error'
export interface RuntimeTaskState { id: string; label: string; state: 'pending' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error'; pid: number | null; message: string; dependencies: string[] }
export interface RuntimeStatus { agent_version: number; orchestrating: boolean; enabled: boolean; reachable: boolean; phase: RuntimePhase; host: string; message: string; supervisor_pid: number | null; tasks: RuntimeTaskState[]; updated_at: string }
export interface RuntimeActionResponse { success: boolean; status: RuntimeStatus }

export const robotApi = {
  status: () => api.get<RobotState>('/system/status').then((response) => response.data),
  moveChassis: (linear: number, angular: number) =>
    api.post<CommandResponse>('/chassis/move', { linear, angular }).then((response) => response.data),
  stopChassis: () => api.post<CommandResponse>('/chassis/stop').then((response) => response.data),
  moveJoint: (joint: number, position: number) =>
    api.post<CommandResponse>('/arm/joint', { joint, position }).then((response) => response.data),
  moveJoints: (positions: number[]) =>
    api.post<CommandResponse>('/arm/joints', { positions }).then((response) => response.data),
  movePose: (pose: Pose) => api.post<CommandResponse>('/arm/pose', pose).then((response) => response.data),
  stopArm: () => api.post<CommandResponse>('/arm/stop').then((response) => response.data),
  openGripper: () => api.post<CommandResponse>('/gripper/open').then((response) => response.data),
  closeGripper: () => api.post<CommandResponse>('/gripper/close').then((response) => response.data),
  stopGripper: () => api.post<CommandResponse>('/gripper/stop').then((response) => response.data),
  visualizationConfig: () => api.get<VisualizationConfig>('/visualization/config').then((response) => response.data),
  map: () => api.get<MapSnapshot>('/visualization/map').then((response) => response.data),
  runtimeStatus: () => api.get<RuntimeStatus>('/runtime/status', { timeout: 10000 }).then((response) => response.data),
  startRuntime: () => api.post<RuntimeActionResponse>('/runtime/start', {}, { timeout: 25000 }).then((response) => response.data),
  stopRuntime: () => api.post<RuntimeActionResponse>('/runtime/stop', {}, { timeout: 25000 }).then((response) => response.data),
  startRuntimeTask: (taskId: string) => api.post<RuntimeActionResponse>(`/runtime/tasks/${taskId}/start`, {}, { timeout: 25000 }).then((response) => response.data),
  stopRuntimeTask: (taskId: string) => api.post<RuntimeActionResponse>(`/runtime/tasks/${taskId}/stop`, {}, { timeout: 25000 }).then((response) => response.data),
  runtimeLogs: () => api.get<{ lines: string[] }>('/runtime/logs', { params: { lines: 160 }, timeout: 12000 }).then((response) => response.data),
}
