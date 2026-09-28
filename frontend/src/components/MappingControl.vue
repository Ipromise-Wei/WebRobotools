<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { robotApi, type RuntimeStatus } from '@/api/robot'

const busy = ref(false)
const error = ref('')
const maps = ref<string[]>([])
const yamlFile = ref<File | null>(null)
const pgmFile = ref<File | null>(null)
const status = ref<RuntimeStatus | null>(null)

const taskState = (id: string) => status.value?.tasks.find((task) => task.id === id)?.state
const automaticRunning = computed(() => ['starting', 'running'].includes(taskState('frontier_exploration') || ''))
const mappingTaskIds = ['chassis', 'lidar', 'localization', 'laser_scan', 'slam', 'telemetry_relay', 'navigation', 'frontier_exploration']
const activeTaskState = (state: string | undefined) => ['starting', 'running', 'stopping'].includes(state || '')
// Stopping must remain available while the profile is still bringing up SLAM
// or Frontier. The old UI only enabled it after SLAM reached running, leaving
// no Web stop path during part of automatic-mapping startup.
const mappingRunning = computed(() => mappingTaskIds.some((id) => activeTaskState(taskState(id))))
const actionError = (reason: unknown) => axios.isAxiosError(reason)
  ? String(reason.response?.data?.detail || reason.message)
  : String(reason)

async function refresh() {
  try {
    const [runtime, library] = await Promise.all([robotApi.runtimeStatus(), robotApi.maps()])
    status.value = runtime
    maps.value = library.maps
  } catch (reason) {
    error.value = actionError(reason)
  }
}

async function run(action: () => Promise<unknown>, confirmText: string) {
  if (busy.value || !window.confirm(confirmText)) return
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (reason) {
    error.value = actionError(reason)
  } finally {
    busy.value = false
    await refresh()
  }
}

function startManual() {
  void run(
    () => robotApi.startManualMapping(),
    '启动手动建图？系统将依次启动底盘、雷达、FAST-LIO、SLAM 与 Nav2。请确认现场安全。',
  )
}

function startAutomatic() {
  void run(
    () => robotApi.startAutomaticMapping(),
    '启动自动建图？机器人将由 Frontier 自动探索未知区域。请清空作业区域并确保物理急停可用。',
  )
}

function stopMapping() {
  void run(
    () => robotApi.stopMapping(),
    '停止建图并关闭本次建图启动的机器人模块？自动建图会先取消 Frontier 目标。',
  )
}

async function saveMap() {
  const name = window.prompt('请输入地图名称（字母、数字、下划线或连字符）：', `map_${new Date().toISOString().slice(0, 10).replaceAll('-', '')}`)
  if (!name || busy.value) return
  busy.value = true
  error.value = ''
  try {
    maps.value = (await robotApi.saveMap(name.trim())).maps
  } catch (reason) {
    error.value = actionError(reason)
  } finally {
    busy.value = false
  }
}

function selectedFile(event: Event, type: 'yaml' | 'pgm') {
  const file = (event.target as HTMLInputElement).files?.[0] || null
  if (type === 'yaml') yamlFile.value = file
  else pgmFile.value = file
}

async function fileAsBase64(file: File): Promise<string> {
  const buffer = await file.arrayBuffer()
  const data = new Uint8Array(buffer)
  let binary = ''
  const chunk = 0x8000
  for (let index = 0; index < data.length; index += chunk) {
    binary += String.fromCharCode(...data.subarray(index, index + chunk))
  }
  return btoa(binary)
}

async function importMap() {
  if (!yamlFile.value || !pgmFile.value || busy.value) {
    error.value = '请选择同一张地图的 YAML 描述文件和 PGM 图像文件。'
    return
  }
  const suggested = yamlFile.value.name.replace(/\.ya?ml$/i, '')
  const name = window.prompt('导入后的地图名称：', suggested)
  if (!name) return
  busy.value = true
  error.value = ''
  try {
    maps.value = (await robotApi.importMap(
      name.trim(), await fileAsBase64(yamlFile.value), await fileAsBase64(pgmFile.value),
    )).maps
  } catch (reason) {
    error.value = actionError(reason)
  } finally {
    busy.value = false
  }
}

onMounted(() => void refresh())
</script>

<template>
  <section class="mapping-control">
    <header><span class="eyebrow">MAPPING</span><h3>建图管理</h3></header>
    <p class="mapping-state">
      {{ automaticRunning ? '自动建图运行中' : mappingRunning ? '手动建图运行中' : '建图未启动' }}
    </p>
    <p v-if="error" class="mapping-error" role="alert">{{ error }}</p>
    <div class="mapping-actions">
      <button :disabled="busy" :class="{ active: mappingRunning && !automaticRunning }" @click="startManual">手动建图</button>
      <button :disabled="busy" :class="{ active: automaticRunning }" @click="startAutomatic">自动建图</button>
      <button class="danger" :disabled="busy || !mappingRunning" @click="stopMapping">停止建图</button>
    </div>
    <div class="map-library">
      <div class="map-library-title"><strong>地图文件</strong><button :disabled="busy || !mappingRunning" @click="saveMap">保存当前地图</button></div>
      <p class="mapping-hint">保存与导入的地图会存放在工控机；导入不会中断当前 SLAM 建图。</p>
      <div class="map-import">
        <label>YAML<input type="file" accept=".yaml,.yml" @change="selectedFile($event, 'yaml')"></label>
        <label>PGM<input type="file" accept=".pgm" @change="selectedFile($event, 'pgm')"></label>
        <button :disabled="busy" @click="importMap">导入地图</button>
      </div>
      <p class="map-list">{{ maps.length ? `已保存：${maps.join('、')}` : '暂无已保存地图' }}</p>
    </div>
  </section>
</template>

<style scoped>
.mapping-control { padding: 12px; border: 1px solid #1d3b50; border-radius: 9px; background: #0a1825; }
header { display: flex; align-items: baseline; gap: 8px; } h3 { margin: 0; font-size: 13px; } .eyebrow { font-size: 8px; letter-spacing: .1em; color: #38cbb5; }
.mapping-state, .mapping-hint, .map-list { margin: 8px 0; font-size: 11px; color: #90a9b9; } .mapping-state { color: #d8edf3; }
.mapping-error { margin: 8px 0; color: #ff8f8f; font-size: 11px; }.mapping-actions, .map-import, .map-library-title { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
button { border: 1px solid #2a536a; border-radius: 5px; padding: 5px 8px; color: #dceef4; background: #10283a; font-size: 11px; cursor: pointer; } button:hover:not(:disabled), button.active { border-color: #35cdb7; color: #58e7d0; } button:disabled { opacity: .45; cursor: not-allowed; } button.danger { border-color: #77414a; color: #ffadb5; }
.map-library { margin-top: 12px; padding-top: 10px; border-top: 1px solid #1d3b50; }.map-library-title { justify-content: space-between; }.map-library-title strong { font-size: 12px; }
.map-import label { display: grid; gap: 2px; color: #9ab1c0; font-size: 10px; }.map-import input { width: 132px; color: #cce0e7; font-size: 9px; }.map-list { word-break: break-word; }
</style>
