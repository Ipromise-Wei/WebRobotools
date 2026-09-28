<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { robotApi, type RuntimePhase, type RuntimeStatus, type RuntimeTaskState } from '@/api/robot'

const emptyStatus: RuntimeStatus = {
  agent_version: 0, orchestrating: false, orchestrating_profile: '', enabled: true, reachable: false, phase: 'offline', host: '', message: '正在连接工控机',
  supervisor_pid: null, tasks: [], updated_at: new Date().toISOString(),
}
const status = ref<RuntimeStatus>(emptyStatus)
const busyTask = ref('')
const basicModulesBusy = ref(false)
const startingAll = ref(false)
const stoppingAll = ref(false)
const error = ref('')
const logs = ref<string[]>([])
const showLogs = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
let refreshInFlight = false

const phaseText: Record<RuntimePhase, string> = {
  disabled: '未启用', unconfigured: '待初始化', offline: '离线', stopped: '全部关闭',
  starting: '启动中', running: '运行中', stopping: '停止中', error: '异常',
}
const hasActiveTasks = computed(() => status.value.tasks.some((task) => ['starting', 'running', 'stopping', 'error'].includes(task.state)))
const legacyCanListed = computed(() => status.value.tasks.some((task) => task.id === 'can0'))
const migrationRequired = computed(() => !!status.value.legacy_can0_active || legacyCanListed.value)
const basicModuleIds = new Set(['chassis', 'lidar', 'localization', 'laser_scan', 'telemetry_relay', 'navigation'])
const standardStackIds = basicModuleIds
const baseTasks = computed(() => status.value.tasks.filter((task) => basicModuleIds.has(task.id)))
const basicModulesActive = computed(() => baseTasks.value.some((task) => ['starting', 'running', 'stopping', 'error'].includes(task.state)))
const basicModulesReady = computed(() => baseTasks.value.length === basicModuleIds.size && baseTasks.value.every((task) => task.state === 'running'))
const standardStackRunning = computed(() => {
  const tasks = status.value.tasks.filter((task) => standardStackIds.has(task.id))
  return tasks.length === standardStackIds.size && tasks.every((task) => task.state === 'running')
})
const mappingTaskIds = new Set(['slam', 'frontier_exploration'])
const visibleTasks = computed(() => status.value.tasks.filter((task) =>
  task.id !== 'can0' && !basicModuleIds.has(task.id) && !mappingTaskIds.has(task.id),
))
const controlsBusy = computed(() => !!busyTask.value || basicModulesBusy.value || startingAll.value || stoppingAll.value || status.value.orchestrating || migrationRequired.value)
const stopControlsBusy = computed(() => !!busyTask.value || basicModulesBusy.value || stoppingAll.value || migrationRequired.value)
const taskNames = computed(() => Object.fromEntries(status.value.tasks.map((task) => [task.id, task.label])))
const errorText = (reason: unknown) => axios.isAxiosError(reason)
  ? String(reason.response?.data?.detail || reason.message)
  : String(reason)
const isOn = (task: RuntimeTaskState) => ['starting', 'running'].includes(task.state)
const hasActiveDependents = (task: RuntimeTaskState) => status.value.tasks.some((candidate) =>
  candidate.dependencies.includes(task.id) && ['starting', 'running', 'stopping'].includes(candidate.state),
)
const dependencyText = (task: RuntimeTaskState) => task.dependencies.length
  ? task.dependencies.map((id) => taskNames.value[id] || id).join(' + ')
  : '独立'

async function refresh(silent = true) {
  if (refreshInFlight) return
  refreshInFlight = true
  try {
    status.value = await robotApi.runtimeStatus()
    if (!silent) error.value = ''
  } catch (reason) {
    status.value = { ...emptyStatus, message: errorText(reason) }
    if (!silent) error.value = errorText(reason)
  } finally { refreshInFlight = false }
}

async function toggleTask(task: RuntimeTaskState) {
  if (controlsBusy.value || task.state === 'stopping') return
  const turningOn = !isOn(task)
  if (!window.confirm(`确定${turningOn ? '开启' : '关闭'}“${task.label}”吗？`)) return
  busyTask.value = task.id
  error.value = ''
  try {
    const response = turningOn
      ? await robotApi.startRuntimeTask(task.id)
      : await robotApi.stopRuntimeTask(task.id)
    status.value = response.status
  } catch (reason) {
    error.value = errorText(reason)
  } finally {
    busyTask.value = ''
    await refresh()
  }
}

async function startAll() {
  if (controlsBusy.value) return
  if (!window.confirm('确定按依赖顺序启动基础功能模块与 Nav2 导航吗？')) return
  startingAll.value = true
  error.value = ''
  try {
    status.value = (await robotApi.startRuntime()).status
  } catch (reason) {
    error.value = errorText(reason)
  } finally {
    startingAll.value = false
    await refresh()
  }
}

async function toggleBasicModules() {
  if (!status.value.enabled || status.value.phase === 'offline') return
  const stopping = basicModulesActive.value
  if (stopping ? stopControlsBusy.value : controlsBusy.value) return
  const confirmText = stopping
    ? '关闭基础功能与 Nav2 会同步停止工控机上的全部 Web 管理 ROS2 进程，包含当前 SLAM 与 Frontier。确定继续吗？'
    : '启动基础功能与 Nav2？系统将按依赖顺序启动底盘、雷达、FAST-LIO、点云转激光、通信中继和 Nav2，不启动 SLAM。请确认现场安全。'
  if (!window.confirm(confirmText)) return
  basicModulesBusy.value = true
  error.value = ''
  try {
    status.value = stopping
      ? (await robotApi.stopRuntime()).status
      : (await robotApi.startBasicRuntime()).status
  } catch (reason) {
    error.value = errorText(reason)
  } finally {
    basicModulesBusy.value = false
    await refresh()
  }
}

async function stopAll() {
  if (migrationRequired.value) return
  if (!window.confirm('确定关闭工控机上的全部 Web 管理 ROS2 进程吗？这会停止 SLAM 地图、Nav2 导航和 Frontier 自动建图。')) return
  stoppingAll.value = true
  error.value = ''
  try {
    status.value = (await robotApi.stopRuntime()).status
  } catch (reason) {
    error.value = errorText(reason)
  } finally {
    stoppingAll.value = false
    await refresh()
  }
}

async function toggleLogs() {
  showLogs.value = !showLogs.value
  if (!showLogs.value) return
  try {
    logs.value = (await robotApi.runtimeLogs()).lines
  } catch (reason) {
    error.value = errorText(reason)
  }
}

onMounted(() => {
  void refresh(false)
  timer = setInterval(() => void refresh(), 5000)
})
onBeforeUnmount(() => timer && clearInterval(timer))
</script>

<template>
  <section class="runtime-inline">
    <header>
      <div><span class="eyebrow">ROS2 MODULES</span><h3>模块控制</h3></div>
      <span class="runtime-phase"><i :class="status.phase"></i>{{ phaseText[status.phase] }}</span>
    </header>

    <p v-if="migrationRequired" class="runtime-error" role="alert">{{ status.legacy_can0_active ? status.message : '后端仍返回旧版 CAN0 任务。为避免误改工控机网卡，模块操作已锁定；请确认现场安全后重启 Web 后端。' }}</p>
    <p v-else-if="status.agent_version < 2 && hasActiveTasks" class="runtime-notice">{{ status.message }}</p>
    <p v-if="error" class="runtime-error">{{ error }}</p>
    <div class="runtime-basic-module">
      <div>
        <strong>基础功能 + Nav2</strong>
        <small>底盘、雷达、FAST-LIO、点云转激光、通信中继、Nav2（默认自启）</small>
      </div>
      <button
        class="module-switch basic-module-switch"
        :class="{ on: basicModulesActive, failed: baseTasks.some((task) => task.state === 'error') }"
        :disabled="(basicModulesActive ? stopControlsBusy : controlsBusy) || !status.enabled || status.phase === 'offline'"
        :aria-label="`${basicModulesActive ? '关闭' : '启动'}基础功能与 Nav2`"
        :title="basicModulesReady ? '基础功能与 Nav2 运行中' : basicModulesActive ? '基础功能与 Nav2 正在启动、停止或异常' : '一键启动基础功能与 Nav2'"
        @click="toggleBasicModules"
      ><i></i></button>
    </div>
    <p class="runtime-basic-note">程序启动后自动初始化，默认不运行 SLAM；关闭此模块才会停止全部 Web 管理进程。</p>
    <div v-if="visibleTasks.length" class="runtime-switches">
      <div v-for="task in visibleTasks" :key="task.id" class="runtime-switch-row">
        <i :class="task.state"></i>
        <span><strong>{{ task.label }}</strong><small>{{ dependencyText(task) }} · {{ task.message }}</small></span>
        <button
          class="module-switch"
          :class="{ on: isOn(task), failed: task.state === 'error' }"
          :disabled="controlsBusy || task.state === 'stopping' || (!isOn(task) ? false : hasActiveDependents(task)) || !status.enabled || status.phase === 'offline'"
          :aria-label="`${isOn(task) ? '关闭' : '开启'}${task.label}`"
          :title="isOn(task) && hasActiveDependents(task) ? '请先停止依赖此模块的任务' : undefined"
          @click="toggleTask(task)"
        ><i></i></button>
      </div>
    </div>

    <footer>
      <span>{{ status.host || '192.168.123.41' }}</span>
      <button
        class="start-all"
        :disabled="controlsBusy || standardStackRunning || !status.enabled || status.phase === 'offline'"
        @click="startAll"
      >{{ startingAll || status.orchestrating ? '启动中…' : '基础+导航' }}</button>
      <button @click="refresh(false)">刷新</button>
      <button @click="toggleLogs">{{ showLogs ? '收起日志' : '日志' }}</button>
      <button class="danger" :disabled="stopControlsBusy || (!hasActiveTasks && !status.orchestrating)" @click="stopAll">全部停止</button>
    </footer>
    <pre v-if="showLogs">{{ logs.length ? logs.join('\n') : '暂无日志' }}</pre>
  </section>
</template>
