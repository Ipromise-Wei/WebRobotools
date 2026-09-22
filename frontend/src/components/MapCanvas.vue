<script setup lang="ts">
import axios from 'axios'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRef, watch } from 'vue'
import { robotApi } from '@/api/robot'
import { useVisualizationStore, type MapSnapshot } from '@/stores/visualization'

const props = defineProps<{ map: MapSnapshot; x: number; y: number; yaw: number; navigationReady: boolean; navigationBlockedReason: string }>()
const visual = useVisualizationStore()
const navigation = toRef(visual, 'navigation')
const root = ref<HTMLElement>()
const canvas = ref<HTMLCanvasElement>()
const zoom = ref(1)
const pan = reactive({ x: 0, y: 0 })
const pointer = reactive({ dragging: false, x: 0, y: 0 })
const cursorWorld = ref<{ x: number; y: number } | null>(null)
const followRobot = ref(false)
const layers = reactive({ grid: true, map: true, path: true, robot: true })
const goalMode = ref(false)
const goalDraft = ref<{ x: number; y: number; yaw: number } | null>(null)
const operationBusy = ref(false)
const operationError = ref('')
const navigationActive = computed(() => ['sending', 'navigating', 'canceling'].includes(navigation.value.phase))
const navigationPhaseLabel = computed(() => ({
  idle: '待命', sending: '发送中', navigating: '导航中', canceling: '取消中',
  succeeded: '已到达', canceled: '已取消', failed: '异常',
})[navigation.value.phase] || '待命')
const navigationHint = computed(() => operationError.value || (goalMode.value
  ? '在地图上点选位置并拖动确定朝向'
  : navigation.value.phase !== 'idle' || props.navigationReady
    ? navigation.value.message
    : props.navigationBlockedReason))
let resizeObserver: ResizeObserver | undefined
let mapTexture: HTMLCanvasElement | undefined
let textureRevision = -1

function geometry() {
  const element = canvas.value
  if (!element || !props.map.width || !props.map.height) return null
  const box = element.getBoundingClientRect()
  const base = Math.min(box.width / props.map.width, box.height / props.map.height)
  const scale = base * zoom.value
  let left = (box.width - props.map.width * scale) / 2 + pan.x
  let top = (box.height - props.map.height * scale) / 2 + pan.y
  if (followRobot.value && props.map.resolution) {
    const robotX = (props.x - props.map.origin_x) / props.map.resolution
    const robotY = props.map.height - (props.y - props.map.origin_y) / props.map.resolution
    left = box.width / 2 - robotX * scale
    top = box.height / 2 - robotY * scale
    pan.x = left - (box.width - props.map.width * scale) / 2
    pan.y = top - (box.height - props.map.height * scale) / 2
  }
  return { box, scale, left, top }
}

function texture() {
  if (mapTexture && textureRevision === props.map.revision) return mapTexture
  const offscreen = document.createElement('canvas')
  offscreen.width = props.map.width
  offscreen.height = props.map.height
  const context = offscreen.getContext('2d')!
  const image = context.createImageData(offscreen.width, offscreen.height)
  props.map.data.forEach((value, index) => {
    const target = ((props.map.height - 1 - Math.floor(index / props.map.width)) * props.map.width + index % props.map.width) * 4
    const shade = value < 0 ? 35 : 235 - Math.round(value * 2.15)
    image.data[target] = value < 0 ? 19 : shade
    image.data[target + 1] = value < 0 ? 23 : shade
    image.data[target + 2] = value < 0 ? 26 : shade
    image.data[target + 3] = 255
  })
  context.putImageData(image, 0, 0)
  mapTexture = offscreen
  textureRevision = props.map.revision
  return offscreen
}

function mapPixel(x: number, y: number, view: NonNullable<ReturnType<typeof geometry>>) {
  return {
    x: view.left + (x - props.map.origin_x) / props.map.resolution * view.scale,
    y: view.top + (props.map.height - (y - props.map.origin_y) / props.map.resolution) * view.scale,
  }
}

function worldAt(event: PointerEvent) {
  const view = geometry()
  const rect = canvas.value?.getBoundingClientRect()
  if (!view || !rect || !props.map.resolution) return null
  const px = (event.clientX - rect.left - view.left) / view.scale
  const py = (event.clientY - rect.top - view.top) / view.scale
  if (px < 0 || py < 0 || px >= props.map.width || py >= props.map.height) return null
  return { x: props.map.origin_x + px * props.map.resolution, y: props.map.origin_y + (props.map.height - py) * props.map.resolution }
}

function drawGoal(context: CanvasRenderingContext2D, x: number, y: number, yaw: number, view: NonNullable<ReturnType<typeof geometry>>, color: string) {
  const point = mapPixel(x, y, view)
  context.save()
  context.translate(point.x, point.y)
  context.rotate(-yaw)
  context.strokeStyle = color
  context.fillStyle = color
  context.lineWidth = 3
  context.beginPath()
  context.arc(0, 0, 8, 0, 2 * Math.PI)
  context.stroke()
  context.beginPath()
  context.moveTo(0, 0)
  context.lineTo(28, 0)
  context.lineTo(20, -6)
  context.moveTo(28, 0)
  context.lineTo(20, 6)
  context.stroke()
  context.restore()
}

function drawGrid(context: CanvasRenderingContext2D, width: number, height: number) {
  const spacing = Math.max(28, 48 * zoom.value)
  const offsetX = ((pan.x % spacing) + spacing) % spacing
  const offsetY = ((pan.y % spacing) + spacing) % spacing
  context.beginPath()
  for (let x = offsetX; x < width; x += spacing) { context.moveTo(x, 0); context.lineTo(x, height) }
  for (let y = offsetY; y < height; y += spacing) { context.moveTo(0, y); context.lineTo(width, y) }
  context.strokeStyle = 'rgba(126, 143, 151, .14)'
  context.lineWidth = 1
  context.stroke()
}

function draw() {
  const element = canvas.value
  if (!element) return
  const box = element.getBoundingClientRect()
  const ratio = devicePixelRatio || 1
  element.width = Math.max(1, Math.round(box.width * ratio))
  element.height = Math.max(1, Math.round(box.height * ratio))
  const context = element.getContext('2d')
  if (!context) return
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.fillStyle = '#0c1114'
  context.fillRect(0, 0, box.width, box.height)
  if (layers.grid) drawGrid(context, box.width, box.height)
  const view = geometry()
  if (!view || !props.map.data.length) {
    context.fillStyle = '#707d83'
    context.textAlign = 'center'
    context.font = '11px system-ui, sans-serif'
    context.fillText('等待 /map 数据', box.width / 2, box.height / 2)
    return
  }
  if (layers.map) {
    context.imageSmoothingEnabled = false
    context.drawImage(texture(), view.left, view.top, props.map.width * view.scale, props.map.height * view.scale)
  }
  if (layers.path && props.map.path.length) {
    context.strokeStyle = '#65a2ff'
    context.lineWidth = 2
    context.beginPath()
    props.map.path.forEach((point, index) => {
      const target = mapPixel(point.x, point.y, view)
      index ? context.lineTo(target.x, target.y) : context.moveTo(target.x, target.y)
    })
    context.stroke()
  }
  if (layers.robot) {
    const robot = mapPixel(props.x, props.y, view)
    context.save()
    context.translate(robot.x, robot.y)
    context.rotate(-props.yaw)
    context.shadowBlur = 0
    context.fillStyle = '#78aa86'
    context.beginPath()
    context.moveTo(13, 0)
    context.lineTo(-8, -8)
    context.lineTo(-5, 0)
    context.lineTo(-8, 8)
    context.closePath()
    context.fill()
    context.restore()
  }
  if (navigation.value.x !== null && navigation.value.y !== null && navigation.value.yaw !== null && navigationActive.value) {
    drawGoal(context, navigation.value.x, navigation.value.y, navigation.value.yaw, view, '#e8aa68')
  }
  if (goalDraft.value) drawGoal(context, goalDraft.value.x, goalDraft.value.y, goalDraft.value.yaw, view, '#f0cb86')
}

function resetView() {
  zoom.value = 1
  pan.x = 0
  pan.y = 0
  followRobot.value = false
  draw()
}

function centerRobot() {
  followRobot.value = true
  draw()
}

function toggleGoalMode() {
  goalMode.value = !goalMode.value
  goalDraft.value = null
  if (goalMode.value) followRobot.value = false
  draw()
}

function wheel(event: WheelEvent) {
  const view = geometry()
  if (!view) return
  followRobot.value = false
  const rect = canvas.value!.getBoundingClientRect()
  const mouseX = event.clientX - rect.left
  const mouseY = event.clientY - rect.top
  const mapX = (mouseX - view.left) / view.scale
  const mapY = (mouseY - view.top) / view.scale
  zoom.value = Math.min(8, Math.max(.35, zoom.value * (event.deltaY < 0 ? 1.15 : .87)))
  const next = geometry()!
  pan.x += mouseX - (next.left + mapX * next.scale)
  pan.y += mouseY - (next.top + mapY * next.scale)
  draw()
}

function pointerDown(event: PointerEvent) {
  if (goalMode.value) {
    const point = worldAt(event)
    if (!point || !props.navigationReady || operationBusy.value) return
    const column = Math.floor((point.x - props.map.origin_x) / props.map.resolution)
    const row = Math.floor((point.y - props.map.origin_y) / props.map.resolution)
    if (props.map.data[row * props.map.width + column] !== 0) {
      operationError.value = '请选择地图中的已知空闲区域'
      return
    }
    operationError.value = ''
    goalDraft.value = { ...point, yaw: props.yaw }
    pointer.dragging = true
    canvas.value?.setPointerCapture(event.pointerId)
    draw()
    return
  }
  followRobot.value = false
  pointer.dragging = true
  pointer.x = event.clientX
  pointer.y = event.clientY
  canvas.value?.setPointerCapture(event.pointerId)
}

function pointerMove(event: PointerEvent) {
  if (goalMode.value && pointer.dragging && goalDraft.value) {
    const point = worldAt(event)
    if (point && Math.hypot(point.x - goalDraft.value.x, point.y - goalDraft.value.y) > .03) {
      goalDraft.value.yaw = Math.atan2(point.y - goalDraft.value.y, point.x - goalDraft.value.x)
      draw()
    }
    return
  }
  if (pointer.dragging) {
    pan.x += event.clientX - pointer.x
    pan.y += event.clientY - pointer.y
    pointer.x = event.clientX
    pointer.y = event.clientY
    draw()
  }
  const view = geometry()
  const rect = canvas.value?.getBoundingClientRect()
  if (!view || !rect || !props.map.resolution) return
  const pixelX = (event.clientX - rect.left - view.left) / view.scale
  const pixelY = (event.clientY - rect.top - view.top) / view.scale
  cursorWorld.value = {
    x: props.map.origin_x + pixelX * props.map.resolution,
    y: props.map.origin_y + (props.map.height - pixelY) * props.map.resolution,
  }
}

function pointerUp(event: PointerEvent) {
  const draft = goalMode.value && pointer.dragging ? goalDraft.value : null
  pointer.dragging = false
  if (canvas.value?.hasPointerCapture(event.pointerId)) canvas.value.releasePointerCapture(event.pointerId)
  if (draft && event.type !== 'pointercancel') void confirmGoal(draft)
  else if (goalMode.value) { goalDraft.value = null; draw() }
}

function errorText(reason: unknown) {
  return axios.isAxiosError(reason) ? String(reason.response?.data?.detail || reason.message) : String(reason)
}

async function confirmGoal(goal: { x: number; y: number; yaw: number }) {
  goalDraft.value = null
  draw()
  if (!window.confirm(`发送 Nav2 目标？\n坐标 (${goal.x.toFixed(2)}, ${goal.y.toFixed(2)}) m\n朝向 ${(goal.yaw * 180 / Math.PI).toFixed(0)}°\n\n请确认路径周围无人且机器人可安全行驶。`)) return
  operationBusy.value = true
  operationError.value = ''
  try {
    navigation.value = await robotApi.navigateTo(goal.x, goal.y, goal.yaw, props.map.frame_id)
    goalMode.value = false
  } catch (reason) { operationError.value = errorText(reason) }
  finally { operationBusy.value = false; draw() }
}

async function cancelGoal() {
  operationBusy.value = true
  operationError.value = ''
  try { navigation.value = await robotApi.cancelNavigation() }
  catch (reason) { operationError.value = errorText(reason) }
  finally { operationBusy.value = false; draw() }
}

async function clearCache() {
  if (!window.confirm('清除 Web 端地图与路径缓存？\n这不会删除工控机上的 SLAM 地图，也不会停止建图。')) return
  operationBusy.value = true
  operationError.value = ''
  try {
    visual.map = await robotApi.clearMapCache()
    mapTexture = undefined
    textureRevision = -1
  } catch (reason) { operationError.value = errorText(reason) }
  finally { operationBusy.value = false }
}

function toggleLayer(layer: keyof typeof layers) {
  layers[layer] = !layers[layer]
  draw()
}

function fullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void root.value?.requestFullscreen()
}

watch(() => [props.map.revision, props.x, props.y, props.yaw], () => nextTick(draw))
watch(navigation, () => nextTick(draw), { deep: true })
onMounted(() => {
  resizeObserver = new ResizeObserver(draw)
  if (root.value) resizeObserver.observe(root.value)
  draw()
})
onBeforeUnmount(() => resizeObserver?.disconnect())
</script>

<template>
  <section ref="root" class="panel map-panel interactive-map">
    <div class="section-title map-title">
      <div><h2>SLAM 地图与路径</h2><span>{{ map.frame_id }} · {{ map.width }}×{{ map.height }}</span></div>
      <div class="map-tools" aria-label="地图视图工具">
        <button class="map-text-tool" :disabled="operationBusy || !map.data.length" title="只清除 Web 内存缓存，不删除 SLAM 地图" @click="clearCache">清地图缓存</button>
        <button :class="{ active: followRobot }" title="跟随机器人" @click="centerRobot">◎</button>
        <button title="复位视图" @click="resetView">↺</button>
        <button title="全屏" @click="fullscreen">⛶</button>
      </div>
    </div>
    <div class="map-viewport">
      <canvas
        ref="canvas"
        :class="{ dragging: pointer.dragging, 'goal-mode': goalMode }"
        @wheel.prevent="wheel"
        @pointerdown="pointerDown"
        @pointermove="pointerMove"
        @pointerup="pointerUp"
        @pointercancel="pointerUp"
        @dblclick="goalMode ? undefined : centerRobot()"
      ></canvas>
      <div class="map-layers">
        <button :class="{ active: layers.grid }" @click="toggleLayer('grid')">网格</button>
        <button :class="{ active: layers.map }" @click="toggleLayer('map')">地图</button>
        <button :class="{ active: layers.path }" @click="toggleLayer('path')">路径</button>
        <button :class="{ active: layers.robot }" @click="toggleLayer('robot')">机器人</button>
      </div>
      <div class="map-nav-card" :class="{ active: goalMode, navigating: navigationActive }">
        <div class="map-nav-head">
          <span>NAV2 · 目标导航</span>
          <strong :class="navigation.phase">{{ navigationPhaseLabel }}</strong>
        </div>
        <p :title="navigationHint">{{ navigationHint }}</p>
        <small v-if="navigation.x !== null && navigation.y !== null && navigation.yaw !== null" class="map-nav-target">X {{ navigation.x.toFixed(2) }} m · Y {{ navigation.y.toFixed(2) }} m · {{ (navigation.yaw * 180 / Math.PI).toFixed(0) }}°</small>
        <div class="map-nav-buttons">
          <button
            :class="{ selected: goalMode }"
            :disabled="(!navigationReady && !goalMode) || operationBusy || navigationActive"
            :aria-pressed="goalMode"
            :title="!navigationReady ? navigationBlockedReason : goalMode ? '退出地图选点' : '在地图上设定目标位置和朝向'"
            @click="toggleGoalMode"
          >{{ goalMode ? '退出选点' : '设置目标' }}</button>
          <button
            class="cancel"
            :disabled="operationBusy || navigation.phase !== 'navigating'"
            @click="cancelGoal"
          >{{ navigation.phase === 'canceling' ? '取消中…' : '取消导航' }}</button>
        </div>
      </div>
      <output v-if="cursorWorld" class="map-coordinate">x {{ cursorWorld.x.toFixed(2) }} · y {{ cursorWorld.y.toFixed(2) }}</output>
      <div class="map-scale">{{ Math.round(zoom * 100) }}%</div>
    </div>
    <div class="map-legend"><span><i class="robot-color"></i>机器人</span><span><i class="path-color"></i>Nav2 路径</span><small>{{ goalMode ? '点击定位置 · 拖动定朝向 · 确认后发送' : '拖拽平移 · 滚轮缩放 · 双击跟随' }}</small></div>
  </section>
</template>
