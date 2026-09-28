<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const props = defineProps<{
  joints: number[]
  poseMode: 'live' | 'target'
  targetDirty: boolean
}>()

const emit = defineEmits<{
  'update:poseMode': [value: 'live' | 'target']
  'resetTarget': []
}>()

const viewport = ref<HTMLDivElement | null>(null)
let renderer: THREE.WebGLRenderer | undefined
let scene: THREE.Scene | undefined
let camera: THREE.PerspectiveCamera | undefined
let controls: OrbitControls | undefined
let resizeObserver: ResizeObserver | undefined
let animationFrame = 0
const jointPivots: THREE.Group[] = []
const displayedAngles = [0, 0, 0, 0, 0, 0]
const targetAngles = [0, 0, 0, 0, 0, 0]

const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0xd8dedb, roughness: 0.48, metalness: 0.28 })
const darkMaterial = new THREE.MeshStandardMaterial({ color: 0x273238, roughness: 0.42, metalness: 0.52 })
const jointMaterial = new THREE.MeshStandardMaterial({ color: 0x7fb58d, roughness: 0.35, metalness: 0.35 })
const toolMaterial = new THREE.MeshStandardMaterial({ color: 0x20292d, roughness: 0.5, metalness: 0.45 })

function mesh(geometry: THREE.BufferGeometry, material = bodyMaterial) {
  const item = new THREE.Mesh(geometry, material)
  item.castShadow = true
  item.receiveShadow = true
  return item
}

function cylinder(radius: number, length: number, material = bodyMaterial) {
  return mesh(new THREE.CylinderGeometry(radius, radius, length, 32), material)
}

function addJointHousing(parent: THREE.Object3D, radius = 0.07, axis: 'y' | 'z' = 'z') {
  const housing = cylinder(radius, 0.1, darkMaterial)
  if (axis === 'z') housing.rotation.x = Math.PI / 2
  parent.add(housing)

  const ring = new THREE.Mesh(
    new THREE.TorusGeometry(radius * 1.02, 0.008, 10, 32),
    jointMaterial,
  )
  if (axis === 'y') ring.rotation.x = Math.PI / 2
  parent.add(ring)
}

function addLink(parent: THREE.Object3D, length: number, radius: number) {
  const link = cylinder(radius, length)
  link.position.y = length / 2
  parent.add(link)
  const spine = mesh(new THREE.BoxGeometry(radius * 1.05, length * 0.82, radius * 1.5), darkMaterial)
  spine.position.y = length / 2
  parent.add(spine)
}

function addAxisMarker(parent: THREE.Object3D) {
  const axes = new THREE.Group()
  const colors = [0xe66c78, 0x7fb58d, 0x5f9fe8]
  const directions = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)]
  directions.forEach((direction, index) => {
    const arrow = new THREE.ArrowHelper(direction, new THREE.Vector3(), 0.105, colors[index], 0.025, 0.014)
    axes.add(arrow)
  })
  parent.add(axes)
}

function buildRobot() {
  if (!scene) return

  const robot = new THREE.Group()
  robot.rotation.y = -0.28
  scene.add(robot)

  const foot = cylinder(0.13, 0.035, darkMaterial)
  foot.position.y = 0.018
  robot.add(foot)
  const base = cylinder(0.105, 0.13)
  base.position.y = 0.095
  robot.add(base)

  const j1 = new THREE.Group()
  j1.position.y = 0.1625
  robot.add(j1)
  jointPivots.push(j1)
  addJointHousing(j1, 0.082, 'y')

  const shoulderOffset = new THREE.Group()
  shoulderOffset.position.x = -0.086
  j1.add(shoulderOffset)
  const shoulderBridge = mesh(new THREE.BoxGeometry(0.17, 0.105, 0.12))
  shoulderBridge.position.x = 0.045
  shoulderOffset.add(shoulderBridge)

  const j2 = new THREE.Group()
  shoulderOffset.add(j2)
  jointPivots.push(j2)
  addJointHousing(j2, 0.078, 'z')
  addLink(j2, 0.38, 0.06)

  const j3 = new THREE.Group()
  j3.position.y = 0.38
  j2.add(j3)
  jointPivots.push(j3)
  addJointHousing(j3, 0.071, 'z')
  addLink(j3, 0.405, 0.052)

  const elbowDogleg = new THREE.Group()
  elbowDogleg.position.set(0.069, 0.405, 0)
  j3.add(elbowDogleg)
  const j4 = new THREE.Group()
  elbowDogleg.add(j4)
  jointPivots.push(j4)
  addJointHousing(j4, 0.061, 'y')
  addLink(j4, 0.115, 0.044)

  const j5 = new THREE.Group()
  j5.position.y = 0.115
  j4.add(j5)
  jointPivots.push(j5)
  addJointHousing(j5, 0.053, 'z')
  addLink(j5, 0.1436, 0.039)

  const j6 = new THREE.Group()
  j6.position.y = 0.1436
  j5.add(j6)
  jointPivots.push(j6)
  addJointHousing(j6, 0.047, 'y')

  const flange = cylinder(0.052, 0.055, toolMaterial)
  flange.position.y = 0.065
  j6.add(flange)
  const tool = mesh(new THREE.CylinderGeometry(0.025, 0.038, 0.12, 24), toolMaterial)
  tool.position.y = 0.15
  j6.add(tool)
  const tip = new THREE.Group()
  tip.position.y = 0.215
  j6.add(tip)
  addAxisMarker(tip)
}

function resetView() {
  if (!camera || !controls) return
  camera.position.set(1.22, 0.86, 1.3)
  controls.target.set(0, 0.48, 0)
  controls.update()
}

function resize() {
  if (!viewport.value || !renderer || !camera) return
  const width = Math.max(1, viewport.value.clientWidth)
  const height = Math.max(1, viewport.value.clientHeight)
  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate() {
  animationFrame = requestAnimationFrame(animate)
  jointPivots.forEach((pivot, index) => {
    const delta = targetAngles[index] - displayedAngles[index]
    displayedAngles[index] += delta * 0.16
    if (index === 0 || index === 3 || index === 5) pivot.rotation.y = displayedAngles[index]
    else pivot.rotation.z = displayedAngles[index]
  })
  controls?.update()
  if (renderer && scene && camera) renderer.render(scene, camera)
}

watch(
  () => props.joints,
  (values) => values.slice(0, 6).forEach((value, index) => { targetAngles[index] = THREE.MathUtils.degToRad(Number(value) || 0) }),
  { deep: true, immediate: true },
)

onMounted(() => {
  if (!viewport.value) return
  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x0c1114, 0.58)
  camera = new THREE.PerspectiveCamera(38, 1, 0.01, 20)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.08
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  viewport.value.appendChild(renderer.domElement)

  scene.add(new THREE.HemisphereLight(0xcbe6dc, 0x12181b, 2.4))
  const keyLight = new THREE.DirectionalLight(0xffffff, 3.1)
  keyLight.position.set(2.2, 3.1, 2.4)
  keyLight.castShadow = true
  scene.add(keyLight)
  const rimLight = new THREE.DirectionalLight(0x62d9d0, 1.3)
  rimLight.position.set(-2, 1.2, -1.4)
  scene.add(rimLight)

  const grid = new THREE.GridHelper(2.4, 24, 0x31595b, 0x1b3033)
  grid.position.y = -0.002
  scene.add(grid)
  const floor = mesh(new THREE.CircleGeometry(1.18, 64), new THREE.MeshStandardMaterial({ color: 0x101719, roughness: 0.92, metalness: 0.05 }))
  floor.rotation.x = -Math.PI / 2
  floor.position.y = -0.006
  scene.add(floor)

  buildRobot()
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.07
  controls.minDistance = 0.72
  controls.maxDistance = 3.4
  controls.maxPolarAngle = Math.PI * 0.93
  resetView()
  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(viewport.value)
  resize()
  animate()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  controls?.dispose()
  renderer?.dispose()
  renderer?.domElement.remove()
  scene?.traverse((item) => {
    if (item instanceof THREE.Mesh) item.geometry.dispose()
  })
})
</script>

<template>
  <div class="arm-teach-3d">
    <div ref="viewport" class="arm-teach-viewport"></div>
    <div class="arm-teach-toolbar">
      <div class="teach-pose-switch" role="group" aria-label="3D 姿态来源">
        <button :class="{ active: poseMode === 'live' }" @click="emit('update:poseMode', 'live')">真机姿态</button>
        <button :class="{ active: poseMode === 'target' }" @click="emit('update:poseMode', 'target')">目标预览</button>
      </div>
      <button class="teach-view-reset" title="恢复默认视角" @click="resetView">复位视角</button>
    </div>
    <div class="arm-teach-state" :class="poseMode">
      <i></i>
      <span>{{ poseMode === 'live' ? 'REAL · 实时关节反馈' : targetDirty ? 'PREVIEW · 待确认目标' : 'PREVIEW · 与真机同步' }}</span>
    </div>
    <div class="arm-teach-readout">
      <span v-for="(joint, index) in joints.slice(0, 6)" :key="index">J{{ index + 1 }} <b>{{ Number(joint).toFixed(1) }}°</b></span>
    </div>
    <p class="arm-teach-hint">左键旋转 · 滚轮缩放 · 右键平移</p>
    <button v-if="poseMode === 'target' && targetDirty" class="teach-discard" @click="emit('resetTarget')">放弃预览并读取真机</button>
  </div>
</template>
