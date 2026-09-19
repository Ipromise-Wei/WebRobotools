<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { MapSnapshot } from '@/stores/visualization'

const props = defineProps<{ map: MapSnapshot; x: number; y: number; yaw: number }>()
const root = ref<HTMLElement>()
const canvas = ref<HTMLCanvasElement>()
const zoom = ref(1)
const pan = reactive({ x: 0, y: 0 })
const pointer = reactive({ dragging: false, x: 0, y: 0 })
const cursorWorld = ref<{ x: number; y: number } | null>(null)
const followRobot = ref(false)
const layers = reactive({ grid: true, map: true, path: true, robot: true })
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
    image.data[target] = value < 0 ? 18 : shade
    image.data[target + 1] = value < 0 ? 34 : shade
    image.data[target + 2] = value < 0 ? 47 : shade
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

function drawGrid(context: CanvasRenderingContext2D, width: number, height: number) {
  const spacing = Math.max(28, 48 * zoom.value)
  const offsetX = ((pan.x % spacing) + spacing) % spacing
  const offsetY = ((pan.y % spacing) + spacing) % spacing
  context.beginPath()
  for (let x = offsetX; x < width; x += spacing) { context.moveTo(x, 0); context.lineTo(x, height) }
  for (let y = offsetY; y < height; y += spacing) { context.moveTo(0, y); context.lineTo(width, y) }
  context.strokeStyle = 'rgba(67, 111, 136, .16)'
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
  context.fillStyle = '#07131f'
  context.fillRect(0, 0, box.width, box.height)
  if (layers.grid) drawGrid(context, box.width, box.height)
  const view = geometry()
  if (!view || !props.map.data.length) {
    context.fillStyle = '#60788c'
    context.textAlign = 'center'
    context.font = '11px Manrope, sans-serif'
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
    context.shadowColor = '#37d6c0'
    context.shadowBlur = 10
    context.fillStyle = '#37d6c0'
    context.beginPath()
    context.moveTo(13, 0)
    context.lineTo(-8, -8)
    context.lineTo(-5, 0)
    context.lineTo(-8, 8)
    context.closePath()
    context.fill()
    context.restore()
  }
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
  followRobot.value = false
  pointer.dragging = true
  pointer.x = event.clientX
  pointer.y = event.clientY
  canvas.value?.setPointerCapture(event.pointerId)
}

function pointerMove(event: PointerEvent) {
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
  pointer.dragging = false
  canvas.value?.releasePointerCapture(event.pointerId)
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
      <div class="map-tools">
        <button :class="{ active: followRobot }" title="跟随机器人" @click="centerRobot">◎</button>
        <button title="复位视图" @click="resetView">↺</button>
        <button title="全屏" @click="fullscreen">⛶</button>
      </div>
    </div>
    <div class="map-viewport">
      <canvas
        ref="canvas"
        :class="{ dragging: pointer.dragging }"
        @wheel.prevent="wheel"
        @pointerdown="pointerDown"
        @pointermove="pointerMove"
        @pointerup="pointerUp"
        @pointercancel="pointerUp"
        @dblclick="centerRobot"
      ></canvas>
      <div class="map-layers">
        <button :class="{ active: layers.grid }" @click="toggleLayer('grid')">网格</button>
        <button :class="{ active: layers.map }" @click="toggleLayer('map')">地图</button>
        <button :class="{ active: layers.path }" @click="toggleLayer('path')">路径</button>
        <button :class="{ active: layers.robot }" @click="toggleLayer('robot')">机器人</button>
      </div>
      <output v-if="cursorWorld" class="map-coordinate">x {{ cursorWorld.x.toFixed(2) }} · y {{ cursorWorld.y.toFixed(2) }}</output>
      <div class="map-scale">{{ Math.round(zoom * 100) }}%</div>
    </div>
    <div class="map-legend"><span><i class="robot-color"></i>机器人</span><span><i class="path-color"></i>Nav2 路径</span><small>拖拽平移 · 滚轮缩放 · 双击跟随</small></div>
  </section>
</template>
