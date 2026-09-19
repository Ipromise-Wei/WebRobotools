<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { robotApi, type RuntimePhase, type RuntimeStatus, type RuntimeTaskState } from '@/api/robot'

const emptyStatus: RuntimeStatus = {
  agent_version: 0, orchestrating: false, enabled: true, reachable: false, phase: 'offline', host: '', message: '正在连接工控机',
  supervisor_pid: null, tasks: [], updated_at: new Date().toISOString(),
}
const status = ref<RuntimeStatus>(emptyStatus)
const busyTask = ref('')
const startingAll = ref(false)
const stoppingAll = ref(false)
const error = ref('')
const logs = ref<string[]>([])
const showLogs = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

const phaseText: Record<RuntimePhase, string> = {
  disabled: '未启用', unconfigured: '待初始化', offline: '离线', stopped: '全部关闭',
  starting: '启动中', running: '运行中', stopping: '停止中', error: '异常',
}
const hasActiveTasks = computed(() => status.value.tasks.some((task) => ['starting', 'running', 'stopping', 'error'].includes(task.state)))
const allRunning = computed(() => status.value.tasks.length > 0 && status.value.tasks.every((task) => task.state === 'running'))
const controlsBusy = computed(() => !!busyTask.value || startingAll.value || stoppingAll.value || status.value.orchestrating)
const taskNames = computed(() => Object.fromEntries(status.value.tasks.map((task) => [task.id, task.label])))
const errorText = (reason: unknown) => axios.isAxiosError(reason)
  ? String(reason.response?.data?.detail || reason.message)
  : String(reason)
const isOn = (task: RuntimeTaskState) => ['starting', 'running'].includes(task.state)
const dependencyText = (task: RuntimeTaskState) => task.dependencies.length
  ? task.dependencies.map((id) => taskNames.value[id] || id).join(' + ')
  : '独立'

async function refresh(silent = true) {
  try {
    status.value = await robotApi.runtimeStatus()
    if (!silent) error.value = ''
  } catch (reason) {
    status.value = { ...emptyStatus, message: errorText(reason) }
    if (!silent) error.value = errorText(reason)
  }
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
  if (!window.confirm('确定按依赖顺序启动全部机器人模块吗？')) return
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

async function stopAll() {
  if (!window.confirm('确定关闭全部机器人模块吗？')) return
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
  timer = setInterval(() => void refresh(), 3000)
})
onBeforeUnmount(() => timer && clearInterval(timer))
</script>

<template>
  <section class="runtime-inline">
    <header>
      <div><span class="eyebrow">ROS2 MODULES</span><h3>模块控制</h3></div>
      <span class="runtime-phase"><i :class="status.phase"></i>{{ phaseText[status.phase] }}</span>
    </header>

    <p v-if="status.agent_version < 2 && hasActiveTasks" class="runtime-notice">{{ status.message }}</p>
    <p v-if="error" class="runtime-error">{{ error }}</p>
    <div class="runtime-switches">
      <div v-for="task in status.tasks" :key="task.id" class="runtime-switch-row">
        <i :class="task.state"></i>
        <span><strong>{{ task.label }}</strong><small>{{ dependencyText(task) }} · {{ task.message }}</small></span>
        <button
          class="module-switch"
          :class="{ on: isOn(task), failed: task.state === 'error' }"
          :disabled="controlsBusy || task.state === 'stopping' || !status.enabled || status.phase === 'offline'"
          :aria-label="`${isOn(task) ? '关闭' : '开启'}${task.label}`"
          @click="toggleTask(task)"
        ><i></i></button>
      </div>
      <p v-if="!status.tasks.length">读取模块清单中……</p>
    </div>

    <footer>
      <span>{{ status.host || '192.168.123.41' }}</span>
      <button
        class="start-all"
        :disabled="controlsBusy || allRunning || !status.enabled || status.phase === 'offline'"
        @click="startAll"
      >{{ startingAll || status.orchestrating ? '启动中…' : '一键全启' }}</button>
      <button @click="refresh(false)">刷新</button>
      <button @click="toggleLogs">{{ showLogs ? '收起日志' : '日志' }}</button>
      <button class="danger" :disabled="stoppingAll || !!busyTask || (!hasActiveTasks && !status.orchestrating)" @click="stopAll">全部停止</button>
    </footer>
    <pre v-if="showLogs">{{ logs.length ? logs.join('\n') : '暂无日志' }}</pre>
  </section>
</template>
