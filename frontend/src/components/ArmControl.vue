<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { robotApi, type ArmConfig } from '@/api/robot'
import { useRobotStore, type Pose } from '@/stores/robot'

const radiansToDegrees = 180 / Math.PI
const degreesToRadians = Math.PI / 180
const poseKeys: (keyof Pose)[] = ['x', 'y', 'z', 'rx', 'ry', 'rz']
const poseLabels: Record<keyof Pose, string> = { x: 'X', y: 'Y', z: 'Z', rx: 'RX', ry: 'RY', rz: 'RZ' }
const defaultConfig: ArmConfig = {
  enabled: false, motion_commands_enabled: false, model: 'RML63', transport: 'industrial_pc', host: '', port: 8080, network_interface: '', expected_tool: '',
  collision_level: 8, joint_speed_percent: 5, pose_speed_percent: 5,
  workspace_min_m: [-.8, -.8, .05], workspace_max_m: [.8, .8, 1],
  max_pose_segment_m: .8, keepout_enabled: false,
  standby_joints_deg: [178, 37.258, -65.159, 4.531, -107.568, 6.608],
  gripper_enabled: false, gripper_commands_enabled: false,
}

const store = useRobotStore()
const config = ref<ArmConfig>(defaultConfig)
const activePanel = ref<'joints' | 'pose'>('joints')
const joints = ref<number[]>([0, 0, 0, 0, 0, 0])
const pose = reactive<Record<keyof Pose, number>>({ x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 })
const jointSpeed = ref(5)
const poseSpeed = ref(5)
const jointDirty = ref(false)
const poseDirty = ref(false)
const connectionAction = ref<'connect' | 'disconnect' | ''>('')

const trueHardwareMode = computed(() => store.state.system.mode === 'ros2')
const toolMatches = computed(() => !config.value.expected_tool || store.state.arm.tool_frame === config.value.expected_tool)
const canMove = computed(() => trueHardwareMode.value && config.value.motion_commands_enabled && store.state.arm.connected && !store.state.arm.moving && store.state.arm.work_frame_safe && toolMatches.value)
const canUseGripper = computed(() => trueHardwareMode.value && config.value.gripper_commands_enabled && store.state.gripper.connected && !store.state.arm.moving)
const lockReason = computed(() => {
  if (!trueHardwareMode.value) return '后端不是 ROS2 真机模式，页面禁止输出机械臂指令'
  if (!config.value.enabled) return '真机机械臂未在服务端配置'
  if (!config.value.motion_commands_enabled) return '服务端已锁定机械臂运动指令'
  if (!store.state.arm.connected) return store.state.arm.error || `无法经工控机 ${config.value.network_interface || '--'} 连接 ${config.value.host}:${config.value.port}`
  if (store.state.arm.moving) return '机械臂正在运动；等待完成或使用停止按钮'
  if (!store.state.arm.work_frame_safe) return `工作坐标系不是零偏移 Base：当前 ${store.state.arm.work_frame || '--'}`
  if (!toolMatches.value) return `工具系不匹配：当前 ${store.state.arm.tool_frame || '--'}，要求 ${config.value.expected_tool}`
  return `Base 工作系 · 碰撞等级 ${config.value.collision_level} · 控制已就绪`
})
const poseReadout = computed(() => {
  const value = store.state.arm.pose
  return [value.x, value.y, value.z].map((item) => `${(item * 1000).toFixed(1)}`).join(' / ')
})

function syncJoints() {
  joints.value = store.state.arm.joints.map((value) => Number(value.toFixed(3)))
  jointDirty.value = false
}

function syncPose() {
  const current = store.state.arm.pose
  pose.x = current.x * 1000
  pose.y = current.y * 1000
  pose.z = current.z * 1000
  pose.rx = current.rx * radiansToDegrees
  pose.ry = current.ry * radiansToDegrees
  pose.rz = current.rz * radiansToDegrees
  poseDirty.value = false
}

watch(() => store.state.arm.joints, () => { if (!jointDirty.value) syncJoints() }, { deep: true })
watch(() => store.state.arm.pose, () => { if (!poseDirty.value) syncPose() }, { deep: true })

function confirmAction(message: string) {
  return canMove.value && window.confirm(`${message}\n\n请确认机械臂工作空间内无人且无障碍物。`)
}

async function toggleArmConnection() {
  if (connectionAction.value || store.busy || !trueHardwareMode.value || !config.value.enabled) return
  const disconnecting = store.state.arm.connected
  if (disconnecting && !window.confirm('确定断开机械臂控制链路吗？\n\n机械臂运动中禁止断开，夹爪 IO 将先释放。')) return
  connectionAction.value = disconnecting ? 'disconnect' : 'connect'
  try {
    const succeeded = await store.command(disconnecting ? robotApi.disconnectArm : robotApi.connectArm)
    if (succeeded && !disconnecting) {
      syncJoints()
      syncPose()
    }
  } finally {
    connectionAction.value = ''
  }
}

async function executeJoints() {
  if (!confirmAction(`以 ${jointSpeed.value}% 速度执行六轴关节运动？`)) return
  if (await store.command(() => robotApi.moveJoints([...joints.value], jointSpeed.value))) {
    jointDirty.value = false
  }
}

async function moveStandby() {
  if (!confirmAction(`以 ${jointSpeed.value}% 速度回到 grasp_studio 待命位？`)) return
  joints.value = [...config.value.standby_joints_deg]
  jointDirty.value = true
  if (await store.command(() => robotApi.moveJoints([...joints.value], jointSpeed.value))) {
    jointDirty.value = false
  }
}

async function executePose() {
  if (!confirmAction(`以 ${poseSpeed.value}% 速度执行笛卡尔直线运动？`)) return
  const target: Pose = {
    x: pose.x / 1000, y: pose.y / 1000, z: pose.z / 1000,
    rx: pose.rx * degreesToRadians, ry: pose.ry * degreesToRadians, rz: pose.rz * degreesToRadians,
  }
  if (await store.command(() => robotApi.movePose(target, poseSpeed.value))) {
    poseDirty.value = false
  }
}

async function gripper(action: 'open' | 'close' | 'stop') {
  if (action !== 'stop' && !window.confirm(`确定${action === 'open' ? '张开' : '闭合'}真机夹爪吗？`)) return
  const command = action === 'open' ? robotApi.openGripper : action === 'close' ? robotApi.closeGripper : robotApi.stopGripper
  await store.command(command)
}

function changeJoint(index: number, value: number) {
  if (!Number.isFinite(value)) return
  joints.value[index] = Math.max(index === 5 ? -360 : -180, Math.min(index === 5 ? 360 : 180, value))
  jointDirty.value = true
}

function changeJointFromInput(index: number, event: Event) {
  changeJoint(index, Number((event.target as HTMLInputElement).value))
}

onMounted(async () => {
  syncJoints()
  syncPose()
  try {
    const armConfig = await robotApi.armConfig()
    config.value = armConfig
    jointSpeed.value = armConfig.joint_speed_percent
    poseSpeed.value = armConfig.pose_speed_percent
  } catch {
    // The global connection banner already reports backend failures.
  }
})
</script>

<template>
  <div class="arm-workspace">
    <section class="panel arm-observation">
      <div class="section-title arm-vision-title">
        <div><span class="eyebrow">ROBOT STATE</span><h2>末端实时状态</h2></div>
        <span>VIDEO OFF</span>
      </div>

      <div class="arm-visual-stage">
        <div class="arm-camera-empty camera-waiting">
          <div class="arm-grid-plane"><i class="axis-x"></i><i class="axis-y"></i><i class="axis-z"></i><b>TCP</b></div>
          <strong>视频实时可视化已关闭</strong>
          <span>相机采集、编码和网络传输均不启动</span>
        </div>
        <div class="vision-hud top">
          <span>REALMAN {{ config.model }} · {{ config.transport === 'industrial_pc' ? `IPC/${config.network_interface || '--'}` : 'DIRECT' }}</span>
          <span>{{ store.state.arm.connected ? 'CTRL LINKED' : 'CTRL OFFLINE' }}</span>
        </div>
        <div class="vision-hud bottom"><span>TCP {{ poseReadout }} mm</span><span>{{ store.state.arm.work_frame || 'NO WORK FRAME' }} / {{ store.state.arm.tool_frame || 'NO TOOL FRAME' }}</span></div>
      </div>

      <div class="arm-joint-telemetry">
        <article v-for="(joint, index) in store.state.arm.joints" :key="index">
          <small>J{{ index + 1 }}</small><strong>{{ joint.toFixed(1) }}°</strong><i><b :style="{ width: `${Math.min(100, Math.abs(joint) / (index === 5 ? 360 : 180) * 100)}%` }"></b></i>
        </article>
      </div>

      <div class="arm-reference-note">
        <span class="eyebrow">GRASP STUDIO PROFILE</span>
        <p>真机配置：工具 +Z 接近，抓取中心偏移 70 mm；当前页面提供安全手动定位、待命位和夹爪 IO，为后续视觉伺服任务保留同一控制约定。</p>
      </div>
    </section>

    <aside class="arm-command-deck">
      <header class="arm-control-header">
        <div><span class="eyebrow">MANIPULATOR CONTROL</span><h3>真机运动控制</h3></div>
        <div class="arm-connection-actions">
          <i :class="{ online: store.state.arm.connected }"></i>
          <button
            type="button"
            :class="{ disconnect: store.state.arm.connected }"
            :disabled="store.busy || !trueHardwareMode || !config.enabled || (store.state.arm.connected && store.state.arm.moving)"
            @click="toggleArmConnection"
          >{{ connectionAction === 'connect' ? '连接中…' : connectionAction === 'disconnect' ? '断开中…' : store.state.arm.connected ? '断开' : '连接机械臂' }}</button>
        </div>
      </header>

      <div class="arm-link-route">
        <span>工控机固定链路</span>
        <strong>{{ config.network_interface || '--' }} → {{ config.host || '--' }}:{{ config.port }}</strong>
      </div>

      <p class="arm-safety-state" :class="{ ready: canMove }"><b>{{ canMove ? '安全条件通过' : '运动锁定' }}</b><span>{{ lockReason }}</span></p>

      <nav class="arm-control-tabs">
        <button :class="{ active: activePanel === 'joints' }" @click="activePanel = 'joints'">关节控制</button>
        <button :class="{ active: activePanel === 'pose' }" @click="activePanel = 'pose'">TCP 位姿</button>
      </nav>

      <div v-if="activePanel === 'joints'" class="arm-control-body joint-editor">
        <label v-for="(joint, index) in joints" :key="index">
          <strong>J{{ index + 1 }}</strong>
          <button @click="changeJoint(index, joint - 1)">−</button>
          <input :value="joint" type="range" :min="index === 5 ? -360 : -180" :max="index === 5 ? 360 : 180" step="0.5" @input="changeJointFromInput(index, $event)" />
          <button @click="changeJoint(index, joint + 1)">＋</button>
          <input :value="joint" type="number" :min="index === 5 ? -360 : -180" :max="index === 5 ? 360 : 180" step="0.1" @input="changeJointFromInput(index, $event)" />
        </label>
        <div class="arm-speed"><span>关节速度</span><input v-model.number="jointSpeed" type="range" min="1" max="20" step="1" /><output>{{ jointSpeed }}%</output></div>
        <div class="arm-action-grid">
          <button :disabled="store.busy" @click="syncJoints">读取当前</button>
          <button :disabled="!canMove || store.busy" @click="moveStandby">回到待命位</button>
          <button class="primary" :disabled="!canMove || store.busy || !jointDirty" @click="executeJoints">执行关节运动</button>
        </div>
      </div>

      <div v-else class="arm-control-body pose-editor">
        <div class="pose-target-grid">
          <label v-for="key in poseKeys" :key="key">
            <span>{{ poseLabels[key] }} <small>{{ ['x','y','z'].includes(key) ? 'mm' : 'deg' }}</small></span>
            <input v-model.number="pose[key]" type="number" :step="['x','y','z'].includes(key) ? 1 : .5" @input="poseDirty = true" />
          </label>
        </div>
        <p class="workspace-range">工作空间 XYZ：{{ config.workspace_min_m.map(v => (v * 1000).toFixed(0)).join(' / ') }} ～ {{ config.workspace_max_m.map(v => (v * 1000).toFixed(0)).join(' / ') }} mm · 单段 ≤ {{ (config.max_pose_segment_m * 1000).toFixed(0) }} mm · 禁区 {{ config.keepout_enabled ? 'ON' : 'OFF' }}</p>
        <div class="arm-speed"><span>直线速度</span><input v-model.number="poseSpeed" type="range" min="1" max="20" step="1" /><output>{{ poseSpeed }}%</output></div>
        <div class="arm-action-grid two">
          <button :disabled="store.busy" @click="syncPose">读取当前</button>
          <button class="primary" :disabled="!canMove || store.busy || !poseDirty" @click="executePose">执行直线运动</button>
        </div>
      </div>

      <section class="arm-gripper-inline">
        <header><div><span class="eyebrow">TOOL IO</span><h3>末端夹爪</h3></div><small>{{ store.state.gripper.connected ? store.state.gripper.status : 'offline' }}</small></header>
        <div><button :disabled="!canUseGripper || store.busy" @click="gripper('open')">张开</button><button :disabled="!canUseGripper || store.busy" @click="gripper('close')">闭合</button><button :disabled="!trueHardwareMode || !config.gripper_enabled || store.busy" @click="gripper('stop')">释放 IO</button></div>
      </section>

      <button class="arm-emergency-stop" :disabled="!trueHardwareMode || !config.enabled" @click="store.stopManipulator">
        <b>■</b><span>停止全部动作<small>机械臂停止 + 夹爪 IO 释放</small></span>
      </button>
    </aside>
  </div>
</template>
