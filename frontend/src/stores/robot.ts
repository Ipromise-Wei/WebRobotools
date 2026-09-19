import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'
import { robotApi } from '@/api/robot'
import { RobotSocket } from '@/websocket/robotSocket'

export interface Pose { x: number; y: number; z: number; rx: number; ry: number; rz: number }
export interface RobotState {
  system: { backend: boolean; ros2: boolean; mode: 'mock' | 'ros2' }
  chassis: { connected: boolean; linear_velocity: number; angular_velocity: number; moving: boolean; x: number; y: number; yaw: number; odom_received: boolean; map_x: number; map_y: number; map_yaw: number; map_pose_received: boolean; battery_percentage: number | null; battery_voltage: number | null }
  arm: { connected: boolean; moving: boolean; joints: number[]; pose: Pose }
  gripper: { connected: boolean; status: 'opened' | 'closed' | 'stopped'; position: number; moving: boolean }
  updated_at: string
}

const emptyState: RobotState = {
  system: { backend: false, ros2: false, mode: 'mock' },
  chassis: { connected: false, linear_velocity: 0, angular_velocity: 0, moving: false, x: 0, y: 0, yaw: 0, odom_received: false, map_x: 0, map_y: 0, map_yaw: 0, map_pose_received: false, battery_percentage: null, battery_voltage: null },
  arm: { connected: false, moving: false, joints: [0, 0, 0, 0, 0, 0], pose: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 } },
  gripper: { connected: false, status: 'stopped', position: 0, moving: false },
  updated_at: new Date().toISOString(),
}

export const useRobotStore = defineStore('robot', () => {
  const state = ref<RobotState>(emptyState)
  const socketConnected = ref(false)
  const busy = ref(false)
  let streamInFlight = false
  const error = ref('')
  const socket = new RobotSocket<RobotState>(
    (nextState) => { state.value = nextState },
    (connected) => { socketConnected.value = connected },
  )

  async function initialize() {
    try { state.value = await robotApi.status() }
    catch { error.value = '无法连接后端，请确认服务已启动。' }
    socket.connect()
  }

  async function command(action: () => Promise<{ state: RobotState }>) {
    busy.value = true
    error.value = ''
    try { state.value = (await action()).state }
    catch (reason) {
      error.value = axios.isAxiosError(reason)
        ? String(reason.response?.data?.detail || reason.message)
        : reason instanceof Error ? reason.message : '命令执行失败'
    }
    finally { busy.value = false }
  }

  async function streamChassis(linear: number, angular: number) {
    if (streamInFlight) return
    streamInFlight = true
    try {
      state.value = (await robotApi.moveChassis(linear, angular)).state
      error.value = ''
    } catch (reason) {
      error.value = axios.isAxiosError(reason)
        ? String(reason.response?.data?.detail || reason.message)
        : reason instanceof Error ? reason.message : '底盘控制失败'
    } finally {
      streamInFlight = false
    }
  }

  async function stopChassisStream() {
    try {
      state.value = (await robotApi.stopChassis()).state
    } catch (reason) {
      error.value = axios.isAxiosError(reason)
        ? String(reason.response?.data?.detail || reason.message)
        : '底盘停止失败'
    }
  }

  return { state, socketConnected, busy, error, initialize, disconnect: () => socket.disconnect(), command, streamChassis, stopChassisStream }
})
