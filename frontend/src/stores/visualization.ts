import { defineStore } from 'pinia'
import { ref } from 'vue'
import { robotApi, type NavigationStatus } from '@/api/robot'

export interface MapSnapshot { frame_id: string; width: number; height: number; resolution: number; origin_x: number; origin_y: number; origin_yaw: number; data: number[]; path: { x: number; y: number }[]; revision: number; updated_at: string }
export interface VisualizationConfig { camera_stream_url: string; camera_enabled: boolean; camera_connected: boolean; camera_serial: string; camera_error: string; map_topic: string; plan_topic: string; motion_commands_enabled: boolean; navigation_ready: boolean; navigation_reason: string }

const emptyMap: MapSnapshot = { frame_id: 'map', width: 0, height: 0, resolution: .05, origin_x: 0, origin_y: 0, origin_yaw: 0, data: [], path: [], revision: 0, updated_at: new Date().toISOString() }

export const useVisualizationStore = defineStore('visualization', () => {
  const map = ref(emptyMap)
  const config = ref<VisualizationConfig>({ camera_stream_url: '', camera_enabled: false, camera_connected: false, camera_serial: '', camera_error: '', map_topic: '/map', plan_topic: '/plan', motion_commands_enabled: false, navigation_ready: false, navigation_reason: '正在连接后端' })
  const navigation = ref<NavigationStatus>({ phase: 'idle', message: '尚未设置导航目标', x: null, y: null, yaw: null })
  let socket: WebSocket | undefined
  let reconnect: number | undefined
  let configPoll: number | undefined
  let navigationPoll: number | undefined
  let configInFlight = false
  let navigationInFlight = false
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
    try { navigation.value = await robotApi.navigationStatus() }
    catch { /* Status polling below retries. */ }
    if (configPoll) clearInterval(configPoll)
    configPoll = window.setInterval(async () => {
      if (configInFlight) return
      configInFlight = true
      try { config.value = await robotApi.visualizationConfig() }
      catch { /* The global robot connection indicator reports backend outages. */ }
      finally { configInFlight = false }
    }, 2000)
    if (navigationPoll) clearInterval(navigationPoll)
    navigationPoll = window.setInterval(async () => {
      if (navigationInFlight) return
      navigationInFlight = true
      try { navigation.value = await robotApi.navigationStatus() }
      catch { /* Global backend state reports outages. */ }
      finally { navigationInFlight = false }
    }, 2000)
  }
  function disconnect() {
    closed = true
    if (reconnect) clearTimeout(reconnect)
    if (configPoll) clearInterval(configPoll)
    if (navigationPoll) clearInterval(navigationPoll)
    socket?.close()
  }
  return { map, config, navigation, initialize, disconnect }
})
