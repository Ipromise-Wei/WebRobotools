<script setup lang="ts">
import { computed } from 'vue'
import ArmControl from '@/components/ArmControl.vue'
import { useRobotStore } from '@/stores/robot'

const store = useRobotStore()
const tcpPosition = computed(() => {
  const pose = store.state.arm.pose
  return `${(pose.x * 1000).toFixed(0)} / ${(pose.y * 1000).toFixed(0)} / ${(pose.z * 1000).toFixed(0)}`
})
</script>

<template>
  <div class="page arm-page">
    <div class="page-heading arm-heading">
      <div><span class="eyebrow">RML63 · TRUE HARDWARE</span><h2>机械臂工作站</h2></div>
      <span class="mode-badge" :class="{ online: store.state.arm.connected }">
        {{ store.state.arm.connected ? (store.state.arm.moving ? 'moving' : 'online') : 'offline' }}
      </span>
    </div>

    <div class="metrics arm-metrics">
      <article><small>控制器</small><strong class="text-metric">{{ store.state.arm.connected ? '已连接' : '未连接' }}</strong></article>
      <article><small>运动状态</small><strong class="text-metric">{{ store.state.arm.moving ? '运动中' : '已停止' }}</strong></article>
      <article><small>TCP XYZ / mm</small><strong class="arm-coordinate">{{ tcpPosition }}</strong></article>
      <article><small>工作系 / 工具系</small><strong class="text-metric">{{ store.state.arm.work_frame || '--' }} / {{ store.state.arm.tool_frame || '--' }}</strong></article>
    </div>

    <ArmControl />
  </div>
</template>
