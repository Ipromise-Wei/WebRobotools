<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import ChassisControl from '@/components/ChassisControl.vue'
import MapCanvas from '@/components/MapCanvas.vue'
import MappingControl from '@/components/MappingControl.vue'
import RuntimeControl from '@/components/RuntimeControl.vue'
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
    <div class="workspace-summary chassis-summary">
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
    </div>

    <div class="chassis-workspace">
      <MapCanvas
        :map="visual.map"
        :x="store.state.chassis.map_pose_received ? store.state.chassis.map_x : store.state.chassis.x"
        :y="store.state.chassis.map_pose_received ? store.state.chassis.map_y : store.state.chassis.y"
        :yaw="store.state.chassis.map_pose_received ? store.state.chassis.map_yaw : store.state.chassis.yaw"
        :navigation-ready="visual.config.navigation_ready"
        :navigation-blocked-reason="visual.config.navigation_reason"
      />

      <div class="chassis-side-stack">
        <aside class="chassis-console">
          <RuntimeControl />
          <MappingControl />
          <div class="console-title"><div><span class="eyebrow">MANUAL DRIVE</span><h3>运动控制</h3></div><i :class="{ online: store.state.chassis.connected }"></i></div>
          <p v-if="store.state.system.mode === 'ros2' && !visual.config.motion_commands_enabled" class="safety-lock">
            <strong>等待安全链路</strong><span>请先开启底盘模块并等待速度看门狗上线</span>
          </p>
          <p v-else-if="['sending', 'navigating', 'canceling'].includes(visual.navigation.phase)" class="safety-lock">
            <strong>Nav2 正在接管底盘</strong><span>手动驾驶已锁定；停止导航后再接管</span>
          </p>
          <ChassisControl :enabled="(store.state.system.mode !== 'ros2' || visual.config.motion_commands_enabled) && !['sending', 'navigating', 'canceling'].includes(visual.navigation.phase)" />
        </aside>
      </div>
    </div>
  </div>
</template>
