import { defineStore } from 'pinia'
import { ref } from 'vue'
import { robotApi } from '@/api/robot'

export interface MapSnapshot { frame_id: string; width: number; height: number; resolution: number; origin_x: number; origin_y: number; data: number[]; path: { x: number; y: number }[]; revision: number; updated_at: string }
export interface VisualizationConfig { camera_stream_url: string; map_topic: string; plan_topic: string; motion_commands_enabled: boolean }

const emptyMap: MapSnapshot = { frame_id: 'map', width: 0, height: 0, resolution: .05, origin_x: 0, origin_y: 0, data: [], path: [], revision: 0, updated_at: new Date().toISOString() }

export const useVisualizationStore = defineStore('visualization', () => {
  const map = ref(emptyMap)
  const config = ref<VisualizationConfig>({ camera_stream_url: '', map_topic: '/map', plan_topic: '/plan', motion_commands_enabled: false })
  let socket: WebSocket | undefined
  let reconnect: number | undefined
  let closed = false

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    socket = new WebSocket(`${protocol}//${location.host}/ws/map`)
    socket.onmessage = (event) => { const msg = JSON.parse(event.data); if (msg.type === 'map') map.value = msg.data }
    socket.onclose = () => { if (!closed) reconnect = window.setTimeout(connect, 2000) }
  }
  async function initialize() {
    [config.value, map.value] = await Promise.all([robotApi.visualizationConfig(), robotApi.map()])
    closed = false; connect()
  }
  function disconnect() { closed = true; if (reconnect) clearTimeout(reconnect); socket?.close() }
  return { map, config, initialize, disconnect }
})
