import { defineStore } from 'pinia'
import { ref } from 'vue'
import { robotApi } from '@/api/robot'
import { RobotSocket } from '@/websocket/robotSocket'

export interface Pose { x: number; y: number; z: number; rx: number; ry: number; rz: number }
export interface RobotState {
  system: { backend: boolean; ros2: boolean; mode: 'mock' | 'ros2' }
  chassis: { connected: boolean; linear_velocity: number; angular_velocity: number; moving: boolean }
  arm: { connected: boolean; moving: boolean; joints: number[]; pose: Pose }
  gripper: { connected: boolean; status: 'opened' | 'closed' | 'stopped'; position: number; moving: boolean }
  updated_at: string
}

const emptyState: RobotState = {
  system: { backend: false, ros2: false, mode: 'mock' },
  chassis: { connected: false, linear_velocity: 0, angular_velocity: 0, moving: false },
  arm: { connected: false, moving: false, joints: [0, 0, 0, 0, 0, 0], pose: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 } },
  gripper: { connected: false, status: 'stopped', position: 0, moving: false },
  updated_at: new Date().toISOString(),
}

export const useRobotStore = defineStore('robot', () => {
  const state = ref<RobotState>(emptyState)
  const socketConnected = ref(false)
  const busy = ref(false)
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
    catch (reason) { error.value = reason instanceof Error ? reason.message : '命令执行失败' }
    finally { busy.value = false }
  }

  return { state, socketConnected, busy, error, initialize, disconnect: () => socket.disconnect(), command }
})

