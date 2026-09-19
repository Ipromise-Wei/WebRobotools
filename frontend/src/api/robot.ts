import axios from 'axios'
import type { Pose, RobotState } from '@/stores/robot'
import type { MapSnapshot, VisualizationConfig } from '@/stores/visualization'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '/api', timeout: 5000 })

export interface CommandResponse { success: boolean; state: RobotState }

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
}
