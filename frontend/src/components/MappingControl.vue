<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { robotApi, type RuntimeStatus } from '@/api/robot'

const busy = ref(false)
const error = ref('')
const status = ref<RuntimeStatus | null>(null)

const taskState = (id: string) => status.value?.tasks.find((task) => task.id === id)?.state
const automaticRunning = computed(() => ['starting', 'running'].includes(taskState('frontier_exploration') || ''))
const mappingTaskIds = ['chassis', 'lidar', 'localization', 'laser_scan', 'slam', 'telemetry_relay', 'navigation', 'frontier_exploration']
const activeTaskState = (state: string | undefined) => ['starting', 'running', 'stopping'].includes(state || '')
// Stopping must remain available while the profile is still bringing up SLAM
// or Frontier. The old UI only enabled it after SLAM reached running, leaving
// no Web stop path during part of automatic-mapping startup.
const mappingRunning = computed(() => mappingTaskIds.some((id) => activeTaskState(taskState(id))))
const runtimeOrchestrating = computed(() => status.value?.orchestrating === true)
const actionError = (reason: unknown) => axios.isAxiosError(reason)
  ? String(reason.response?.data?.detail || reason.message)
  : String(reason)

async function refresh() {
  try {
    status.value = await robotApi.runtimeStatus()
  } catch (reason) {
    error.value = actionError(reason)
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
    true,
  )
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
      <button :disabled="busy || runtimeOrchestrating" :class="{ active: mappingRunning && !automaticRunning }" @click="startManual">手动建图</button>
      <button :disabled="busy || runtimeOrchestrating" :class="{ active: automaticRunning }" @click="startAutomatic">自动建图</button>
      <button class="danger" :disabled="busy || !mappingRunning" @click="stopMapping">停止建图</button>
    </div>
  </section>
</template>

<style scoped>
.mapping-control { padding: 12px; border: 1px solid #1d3b50; border-radius: 9px; background: #0a1825; }
header { display: flex; align-items: baseline; gap: 8px; } h3 { margin: 0; font-size: 13px; } .eyebrow { font-size: 8px; letter-spacing: .1em; color: #38cbb5; }
.mapping-state { margin: 8px 0; font-size: 11px; color: #d8edf3; }
.mapping-error { margin: 8px 0; color: #ff8f8f; font-size: 11px; }.mapping-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
button { border: 1px solid #2a536a; border-radius: 5px; padding: 5px 8px; color: #dceef4; background: #10283a; font-size: 11px; cursor: pointer; } button:hover:not(:disabled), button.active { border-color: #35cdb7; color: #58e7d0; } button:disabled { opacity: .45; cursor: not-allowed; } button.danger { border-color: #77414a; color: #ffadb5; }
</style>
