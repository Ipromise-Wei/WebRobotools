<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { robotApi, type RuntimeStatus } from '@/api/robot'

const busy = ref(false)
const error = ref('')
const status = ref<RuntimeStatus | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | undefined
let refreshInFlight = false

const taskState = (id: string) => status.value?.tasks.find((task) => task.id === id)?.state
const automaticRunning = computed(() => ['starting', 'running'].includes(taskState('frontier_exploration') || ''))
const activeTaskState = (state: string | undefined) => ['starting', 'running', 'stopping'].includes(state || '')
const slamRunning = computed(() => activeTaskState(taskState('slam')))
const requestedProfile = computed(() => status.value?.orchestrating_profile || '')
const automaticSelected = computed(() => automaticRunning.value || requestedProfile.value === 'automatic_mapping')
const manualSelected = computed(() => !automaticSelected.value && (slamRunning.value || requestedProfile.value === 'manual_mapping'))
const baseTaskIds = ['chassis', 'lidar', 'localization', 'laser_scan', 'telemetry_relay', 'navigation']
const baseReady = computed(() => baseTaskIds.every((id) => taskState(id) === 'running'))
const runtimeOrchestrating = computed(() => status.value?.orchestrating === true)
const manualDisabled = computed(() => busy.value || (!manualSelected.value && (!baseReady.value || runtimeOrchestrating.value)))
const automaticDisabled = computed(() => busy.value || (!automaticSelected.value && (!baseReady.value || runtimeOrchestrating.value)))
const actionError = (reason: unknown) => axios.isAxiosError(reason)
  ? String(reason.response?.data?.detail || reason.message)
  : String(reason)

async function refresh() {
  if (refreshInFlight) return
  refreshInFlight = true
  try {
    status.value = await robotApi.runtimeStatus()
  } catch (reason) {
    error.value = actionError(reason)
  } finally {
    refreshInFlight = false
  }
}

async function run(action: () => Promise<unknown>, confirmText: string, allowDuringOrchestration = false) {
  if (busy.value || (!allowDuringOrchestration && runtimeOrchestrating.value) || !window.confirm(confirmText)) return
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

function toggleManual() {
  if (manualSelected.value) {
    void run(
      () => robotApi.stopMapping(),
      '关闭手动建图？SLAM 将停止且页面地图会清空，底盘、传感器、通信中继和 Nav2 继续运行。',
      true,
    )
    return
  }
  void run(
    () => robotApi.startManualMapping(),
    automaticSelected.value
      ? '切换为手动建图？系统只停止 Frontier，保留当前 SLAM 地图，随后可使用手柄继续建图。'
      : '开启手动建图？系统只增加 SLAM 模块，底盘、传感器、通信中继和 Nav2 保持运行。',
  )
}

function toggleAutomatic() {
  if (automaticSelected.value) {
    void run(
      () => robotApi.stopMapping(),
      '关闭自动建图？Frontier 和 SLAM 将停止且页面地图会清空，基础功能与 Nav2 继续运行。',
      true,
    )
    return
  }
  void run(
    () => robotApi.startAutomaticMapping(),
    manualSelected.value
      ? '在当前地图上开启自动建图？系统只增加 Frontier 自动探索模块，当前 SLAM 地图会继续使用。请确保物理急停可用。'
      : '开启自动建图？系统将依次增加 SLAM 和 Frontier 模块。请清空作业区域并确保物理急停可用。',
  )
}

onMounted(() => {
  void refresh()
  refreshTimer = setInterval(() => void refresh(), 3000)
})
onBeforeUnmount(() => refreshTimer && clearInterval(refreshTimer))
</script>

<template>
  <section class="mapping-control">
    <header><span class="eyebrow">MAPPING</span><h3>建图管理</h3></header>
    <p class="mapping-state">
      {{ automaticSelected ? (automaticRunning ? '自动建图运行中' : '自动建图启动中') : manualSelected ? (runtimeOrchestrating ? '手动建图启动中' : '手动建图运行中') : baseReady ? '未选择建图，可手动驾驶' : '基础功能与 Nav2 初始化中' }}
    </p>
    <p class="mapping-hint">默认不运行 SLAM：手柄只驾驶底盘，不会绘制地图。勾选手动或自动建图才启动建图模块。</p>
    <p v-if="error" class="mapping-error" role="alert">{{ error }}</p>
    <div class="mapping-actions">
      <label class="mapping-option" :class="{ active: manualSelected, disabled: manualDisabled }">
        <input type="checkbox" :checked="manualSelected" :disabled="manualDisabled" @change="toggleManual">
        <span>手动建图</span>
      </label>
      <label class="mapping-option" :class="{ active: automaticSelected, disabled: automaticDisabled }">
        <input type="checkbox" :checked="automaticSelected" :disabled="automaticDisabled" @change="toggleAutomatic">
        <span>自动建图</span>
      </label>
    </div>
  </section>
</template>

<style scoped>
.mapping-control { padding: 12px; border: 1px solid #1d3b50; border-radius: 9px; background: #0a1825; }
header { display: flex; align-items: baseline; gap: 8px; } h3 { margin: 0; font-size: 13px; } .eyebrow { font-size: 8px; letter-spacing: .1em; color: #38cbb5; }
.mapping-state { margin: 8px 0; font-size: 11px; color: #d8edf3; }
.mapping-hint { margin: 0 0 8px; color: #87a8b6; font-size: 9px; line-height: 1.45; }
.mapping-error { margin: 8px 0; color: #ff8f8f; font-size: 11px; }.mapping-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.mapping-option { display: flex; align-items: center; gap: 6px; border: 1px solid #2a536a; border-radius: 5px; padding: 6px 9px; color: #dceef4; background: #10283a; font-size: 11px; cursor: pointer; }
.mapping-option:hover:not(.disabled), .mapping-option.active { border-color: #35cdb7; color: #58e7d0; }
.mapping-option.disabled { opacity: .45; cursor: not-allowed; }
.mapping-option input { margin: 0; accent-color: #35cdb7; }
</style>
