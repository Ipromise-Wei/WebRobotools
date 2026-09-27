import { defineStore } from 'pinia'
import { ref } from 'vue'
import { robotApi, type NavigationStatus } from '@/api/robot'
import { decodeMapSnapshot, emptyMap, type MapSnapshot, type MapWireSnapshot } from '@/mapTransport'

export type { MapSnapshot } from '@/mapTransport'
export interface VisualizationConfig { camera_stream_url: string; camera_enabled: boolean; camera_connected: boolean; camera_serial: string; camera_error: string; map_topic: string; plan_topic: string; motion_commands_enabled: boolean; navigation_ready: boolean; navigation_reason: string }

export const useVisualizationStore = defineStore('visualization', () => {
  const map = ref(emptyMap)
  const config = ref<VisualizationConfig>({ camera_stream_url: '', camera_enabled: false, camera_connected: false, camera_serial: '', camera_error: '', map_topic: '/webrobot/web_map', plan_topic: '/webrobot/web_plan', motion_commands_enabled: false, navigation_ready: false, navigation_reason: '正在连接后端' })
  const navigation = ref<NavigationStatus>({ phase: 'idle', message: '尚未设置导航目标', x: null, y: null, yaw: null })
  let socket: WebSocket | undefined
  let reconnect: number | undefined
  let configPoll: number | undefined
  let navigationPoll: number | undefined
  let configInFlight = false
  let navigationInFlight = false
  let pendingMap: MapWireSnapshot | undefined
  let mapDecoding = false
  let closed = false

  function acceptMap(next: MapSnapshot) {
    if (next.revision > map.value.revision) {
      map.value = next
    } else if (next.revision === map.value.revision && next.path_revision >= map.value.path_revision) {
      map.value = next
    }
  }

  async function queueMap(payload: MapWireSnapshot) {
    pendingMap = payload
    if (mapDecoding) return
    mapDecoding = true
    try {
      while (pendingMap) {
        const next = pendingMap
        pendingMap = undefined
        acceptMap(await decodeMapSnapshot(next))
      }
    } catch {
      // The next map revision can recover from one corrupted network frame.
    } finally { mapDecoding = false }
  }

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    socket = new WebSocket(`${protocol}//${location.host}/ws/map`)
    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'map') void queueMap(msg.data as MapWireSnapshot)
      else if (msg.type === 'path' && msg.data.path_revision >= map.value.path_revision) {
        map.value = { ...map.value, path: msg.data.path, path_revision: msg.data.path_revision }
      }
    }
    socket.onclose = () => { if (!closed) reconnect = window.setTimeout(connect, 2000) }
  }
  async function initialize() {
    closed = false
    connect()
    try { config.value = await robotApi.visualizationConfig() }
    catch { /* The periodic refresh below retries after backend startup. */ }
    try {
      const next = await robotApi.map()
      acceptMap(next)
    }
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
