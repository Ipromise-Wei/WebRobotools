<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import CameraPanel from '@/components/CameraPanel.vue'
import ChassisControl from '@/components/ChassisControl.vue'
import MapCanvas from '@/components/MapCanvas.vue'
import { useRobotStore } from '@/stores/robot'
import { useVisualizationStore } from '@/stores/visualization'

const store = useRobotStore()
const visual = useVisualizationStore()
const battery = computed(() => {
  const value = store.state.chassis.battery_percentage
  if (value == null) return '--'
  return `${Math.round(value <= 1 ? value * 100 : value)}%`
})

onMounted(() => void visual.initialize())
onBeforeUnmount(() => visual.disconnect())
</script>

<template>
  <div class="page chassis-page">
    <div class="page-heading chassis-heading">
      <div><span class="eyebrow">MINI V3</span><h2>移动底盘</h2></div>
      <span class="mode-badge">{{ store.state.chassis.connected ? 'online' : 'offline' }}</span>
    </div>

    <div class="metrics chassis-metrics">
      <article><small>线速度</small><strong>{{ store.state.chassis.linear_velocity.toFixed(2) }}</strong><span>m/s</span></article>
      <article><small>角速度</small><strong>{{ store.state.chassis.angular_velocity.toFixed(2) }}</strong><span>rad/s</span></article>
      <article><small>电池</small><strong class="text-metric">{{ battery }}</strong></article>
      <article><small>运动状态</small><strong class="text-metric">{{ store.state.chassis.moving ? '运动中' : '静止' }}</strong></article>
    </div>

    <div class="chassis-workspace">
      <div class="visual-deck">
        <MapCanvas
          :map="visual.map"
          :x="store.state.chassis.map_pose_received ? store.state.chassis.map_x : store.state.chassis.x"
          :y="store.state.chassis.map_pose_received ? store.state.chassis.map_y : store.state.chassis.y"
          :yaw="store.state.chassis.map_pose_received ? store.state.chassis.map_yaw : store.state.chassis.yaw"
        />
        <CameraPanel :url="visual.config.camera_stream_url" />
      </div>

      <aside class="chassis-console">
        <div class="console-title"><div><span class="eyebrow">MANUAL DRIVE</span><h3>运动控制</h3></div><i :class="{ online: store.state.chassis.connected }"></i></div>
        <p v-if="store.state.system.mode === 'ros2' && !visual.config.motion_commands_enabled" class="safety-lock">
          <strong>安全锁定</strong><span>完成超时停车保护后启用实车指令</span>
        </p>
        <ChassisControl />
      </aside>
    </div>
  </div>
</template>
