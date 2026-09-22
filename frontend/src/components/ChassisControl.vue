<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRobotStore } from '@/stores/robot'
import { useVisualizationStore } from '@/stores/visualization'

const props = defineProps<{ enabled?: boolean }>()
const store = useRobotStore()
const visual = useVisualizationStore()
const root = ref<HTMLElement>()
const pad = ref<HTMLElement>()
const controlMode = ref<'joystick' | 'keyboard'>('keyboard')
const active = ref(false)
const inputMode = ref<'pointer' | 'keyboard' | ''>('')
const linearMax = ref(0.3)
const angularMax = ref(0.8)
const sensitivity = ref(0.8)
const knob = reactive({ x: 0, y: 0 })
const command = reactive({ linear: 0, angular: 0 })
const pressedKeys = reactive(new Set<string>())
let streamTimer: number | undefined

const knobStyle = computed(() => ({ transform: `translate(${knob.x}px, ${knob.y}px)` }))
const effectiveLinear = computed(() => linearMax.value * sensitivity.value)
const effectiveAngular = computed(() => angularMax.value * sensitivity.value)
const navigationActive = computed(() => ['sending', 'navigating', 'canceling'].includes(visual.navigation.phase))

function axis(value: number) {
  const deadzone = 0.08
  const magnitude = Math.abs(value)
  if (magnitude <= deadzone) return 0
  return Math.sign(value) * (magnitude - deadzone) / (1 - deadzone)
}

function setCommand(x: number, y: number) {
  command.linear = -axis(y) * effectiveLinear.value
  command.angular = -axis(x) * effectiveAngular.value
}

function transmit() {
  if (!active.value || !props.enabled) return
  void store.streamChassis(command.linear, command.angular)
}

function beginStreaming() {
  transmit()
  if (!streamTimer) streamTimer = window.setInterval(transmit, 100)
}

function clearStreaming() {
  if (streamTimer) clearInterval(streamTimer)
  streamTimer = undefined
}

function stopDrive(sendStop = true) {
  const wasActive = active.value
  active.value = false
  inputMode.value = ''
  pressedKeys.clear()
  knob.x = 0
  knob.y = 0
  setCommand(0, 0)
  clearStreaming()
  if (sendStop && wasActive) void store.stopChassisStream()
}

function updatePointer(event: PointerEvent) {
  const element = pad.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  const radius = Math.min(rect.width, rect.height) / 2 - 18
  let dx = event.clientX - (rect.left + rect.width / 2)
  let dy = event.clientY - (rect.top + rect.height / 2)
  const distance = Math.hypot(dx, dy)
  if (distance > radius) {
    dx = dx / distance * radius
    dy = dy / distance * radius
  }
  knob.x = dx
  knob.y = dy
  setCommand(dx / radius, dy / radius)
}

function pointerDown(event: PointerEvent) {
  if (!props.enabled || controlMode.value !== 'joystick') return
  event.preventDefault()
  root.value?.focus()
  active.value = true
  inputMode.value = 'pointer'
  pad.value?.setPointerCapture(event.pointerId)
  updatePointer(event)
  beginStreaming()
}

function pointerMove(event: PointerEvent) {
  if (active.value && inputMode.value === 'pointer') updatePointer(event)
}

function pointerUp(event: PointerEvent) {
  if (pad.value?.hasPointerCapture(event.pointerId)) pad.value.releasePointerCapture(event.pointerId)
  if (inputMode.value === 'pointer') stopDrive()
}

function updateKeyboard() {
  const left = pressedKeys.has('arrowleft') || pressedKeys.has('a')
  const right = pressedKeys.has('arrowright') || pressedKeys.has('d')
  const forward = pressedKeys.has('arrowup') || pressedKeys.has('w')
  const reverse = pressedKeys.has('arrowdown') || pressedKeys.has('s')
  const x = (left ? -1 : 0) + (right ? 1 : 0)
  const y = (forward ? -1 : 0) + (reverse ? 1 : 0)
  const magnitude = Math.max(1, Math.hypot(x, y))
  knob.x = x / magnitude * 44
  knob.y = y / magnitude * 44
  setCommand(x / magnitude, y / magnitude)
}

function keyDown(event: KeyboardEvent) {
  const key = event.key.toLowerCase()
  if (key === ' ') {
    event.preventDefault()
    emergencyStop()
    return
  }
  const driveKeys = ['arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'w', 'a', 's', 'd']
  if (!props.enabled || controlMode.value !== 'keyboard' || !driveKeys.includes(key) || event.repeat) return
  event.preventDefault()
  pressedKeys.add(key)
  active.value = true
  inputMode.value = 'keyboard'
  updateKeyboard()
  beginStreaming()
}

function directionActive(direction: 'up' | 'down' | 'left' | 'right') {
  const aliases = {
    up: ['arrowup', 'w'], down: ['arrowdown', 's'],
    left: ['arrowleft', 'a'], right: ['arrowright', 'd'],
  }
  return aliases[direction].some((key) => pressedKeys.has(key))
}

function selectMode(mode: 'joystick' | 'keyboard') {
  if (controlMode.value === mode) {
    void nextTick(() => root.value?.focus())
    return
  }
  stopDrive()
  controlMode.value = mode
  void nextTick(() => root.value?.focus())
}

function keyUp(event: KeyboardEvent) {
  const key = event.key.toLowerCase()
  if (!pressedKeys.has(key)) return
  event.preventDefault()
  pressedKeys.delete(key)
  if (!pressedKeys.size) stopDrive()
  else updateKeyboard()
}

function emergencyStop() {
  stopDrive(false)
  void store.stopChassisStream()
}

function visibilityChanged() {
  if (document.hidden) stopDrive()
}

function loseWindowFocus() {
  stopDrive()
}

watch(() => props.enabled, (enabled) => { if (!enabled) stopDrive() })
onMounted(() => {
  window.addEventListener('blur', loseWindowFocus)
  document.addEventListener('visibilitychange', visibilityChanged)
})
onBeforeUnmount(() => {
  window.removeEventListener('blur', loseWindowFocus)
  document.removeEventListener('visibilitychange', visibilityChanged)
  stopDrive()
})
</script>

<template>
  <section
    ref="root"
    class="control-panel joystick-control"
    :class="{ active, locked: !enabled }"
    tabindex="0"
    @keydown="keyDown"
    @keyup="keyUp"
    @blur="stopDrive()"
  >
    <header class="drive-mode-bar">
      <span>控制方式<small>{{ controlMode === 'keyboard' ? '方向键持续控制' : '二维比例控制' }}</small></span>
      <div class="drive-mode-tabs" role="tablist" aria-label="底盘控制方式">
        <button :class="{ active: controlMode === 'keyboard' }" type="button" @click="selectMode('keyboard')">⌨ 方向键</button>
        <button :class="{ active: controlMode === 'joystick' }" type="button" @click="selectMode('joystick')">● 摇杆</button>
      </div>
    </header>

    <div v-if="controlMode === 'joystick'" class="drive-input-stage joystick-side">
      <div
        ref="pad"
        class="joystick-pad"
        @pointerdown="pointerDown"
        @pointermove="pointerMove"
        @pointerup="pointerUp"
        @pointercancel="pointerUp"
      >
        <span class="axis vertical"></span><span class="axis horizontal"></span>
        <i class="north">前</i><i class="south">后</i><i class="west">左</i><i class="east">右</i>
        <b class="joystick-knob" :style="knobStyle"><span></span></b>
      </div>
      <small>{{ enabled ? '按住并拖动 · 松手即停' : '等待速度看门狗上线' }}</small>
    </div>

    <div v-else class="drive-input-stage keyboard-side" @click="root?.focus()">
      <div class="keyboard-keys" aria-hidden="true">
        <kbd class="key-up" :class="{ active: directionActive('up') }"><b>↑</b><small>前进</small></kbd>
        <kbd class="key-left" :class="{ active: directionActive('left') }"><b>←</b><small>左转</small></kbd>
        <kbd class="key-down" :class="{ active: directionActive('down') }"><b>↓</b><small>后退</small></kbd>
        <kbd class="key-right" :class="{ active: directionActive('right') }"><b>→</b><small>右转</small></kbd>
      </div>
      <small>{{ enabled ? '按住方向键 · 可组合转弯' : '等待速度看门狗上线' }}</small>
    </div>

    <div class="drive-settings">
      <div class="command-readout">
        <span><small>线速度</small><strong>{{ command.linear.toFixed(2) }}</strong><i>m/s</i></span>
        <span><small>角速度</small><strong>{{ command.angular.toFixed(2) }}</strong><i>rad/s</i></span>
      </div>
      <label>线速度上限 <output>{{ linearMax.toFixed(1) }} m/s</output><input v-model.number="linearMax" type="range" min="0.1" max="1" step="0.1" /></label>
      <label>角速度上限 <output>{{ angularMax.toFixed(1) }} rad/s</output><input v-model.number="angularMax" type="range" min="0.1" max="2" step="0.1" /></label>
      <div class="sensitivity"><span>灵敏度</span><button v-for="value in [.25,.5,.8,1]" :key="value" :class="{ active: sensitivity === value }" @click="sensitivity = value">{{ value * 100 }}%</button></div>
      <button class="emergency-stop" @click="emergencyStop"><b>■</b> {{ navigationActive ? '停止导航' : '停止运动' }} <small>{{ navigationActive ? 'NAV2' : 'SPACE' }}</small></button>
      <p>{{ controlMode === 'keyboard' ? '点击控制区后使用 ↑ ↓ ← →，亦支持 W/A/S/D' : '拖动距离决定速度，斜向拖动可边走边转' }}</p>
    </div>
  </section>
</template>
