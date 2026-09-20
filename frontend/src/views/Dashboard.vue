<script setup lang="ts">
import { computed } from 'vue'
import DeviceStatus from '@/components/DeviceStatus.vue'
import SystemLog from '@/components/SystemLog.vue'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
const connectedCount = computed(() => [
  store.state.chassis.connected,
  store.state.arm.connected,
  store.state.gripper.connected,
].filter(Boolean).length)
</script>

<template>
  <div class="page"><div class="page-heading"><div><span class="eyebrow">SYSTEM OVERVIEW</span><h2>运行总览</h2></div><span class="mode-badge">{{ store.state.system.mode === 'ros2' ? 'true hardware' : 'configuration locked' }}</span></div>
    <section class="hero"><div><span class="eyebrow">HARDWARE OPERATIONS</span><h2>农业机器人<br />真机协同工作站</h2><p>统一监视移动底盘、RML63 机械臂与末端夹爪的真实链路状态。</p></div><div class="orbit"><span>{{ connectedCount }}</span><small>CONNECTED</small></div></section>
    <div class="device-grid">
      <DeviceStatus name="移动底盘" model="MINI V3" :connected="store.state.chassis.connected" :detail="store.state.chassis.moving ? '运动中' : '静止'" />
      <DeviceStatus name="机械臂" model="RML63 · 6 AXIS" :connected="store.state.arm.connected" :detail="store.state.arm.moving ? '运动中' : '静止'" accent="#79a7ff" />
      <DeviceStatus name="夹爪" model="AUTONOMOUS GRIPPER" :connected="store.state.gripper.connected" :detail="store.state.gripper.status" accent="#edb75b" />
    </div>
    <SystemLog :entries="['后端服务运行正常', `设备环境：${store.state.system.mode === 'ros2' ? 'ROS2 真机' : '非真机配置（运动锁定）'}`, store.socketConnected ? 'WebSocket 实时链路已建立' : '等待实时链路']" />
  </div>
</template>
