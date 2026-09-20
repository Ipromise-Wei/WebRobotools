import { defineStore } from 'pinia'
import { ref } from 'vue'
import { robotApi } from '@/api/robot'

export interface MapSnapshot { frame_id: string; width: number; height: number; resolution: number; origin_x: number; origin_y: number; data: number[]; path: { x: number; y: number }[]; revision: number; updated_at: string }
export interface VisualizationConfig { camera_stream_url: string; camera_enabled: boolean; camera_connected: boolean; camera_serial: string; camera_error: string; map_topic: string; plan_topic: string; motion_commands_enabled: boolean }

const emptyMap: MapSnapshot = { frame_id: 'map', width: 0, height: 0, resolution: .05, origin_x: 0, origin_y: 0, data: [], path: [], revision: 0, updated_at: new Date().toISOString() }

export const useVisualizationStore = defineStore('visualization', () => {
  const map = ref(emptyMap)
  const config = ref<VisualizationConfig>({ camera_stream_url: '', camera_enabled: false, camera_connected: false, camera_serial: '', camera_error: '', map_topic: '/map', plan_topic: '/plan', motion_commands_enabled: false })
  let socket: WebSocket | undefined
  let reconnect: number | undefined
  let configPoll: number | undefined
  let closed = false

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    socket = new WebSocket(`${protocol}//${location.host}/ws/map`)
    socket.onmessage = (event) => { const msg = JSON.parse(event.data); if (msg.type === 'map') map.value = msg.data }
    socket.onclose = () => { if (!closed) reconnect = window.setTimeout(connect, 2000) }
  }
  async function initialize() {
    closed = false
    connect()
    try { config.value = await robotApi.visualizationConfig() }
    catch { /* The periodic refresh below retries after backend startup. */ }
    try { map.value = await robotApi.map() }
    catch { /* The map WebSocket retries independently. */ }
    if (configPoll) clearInterval(configPoll)
    configPoll = window.setInterval(async () => {
      try { config.value = await robotApi.visualizationConfig() }
      catch { /* The global robot connection indicator reports backend outages. */ }
    }, 1000)
  }
  function disconnect() {
    closed = true
    if (reconnect) clearTimeout(reconnect)
    if (configPoll) clearInterval(configPoll)
    socket?.close()
  }
  return { map, config, initialize, disconnect }
})
