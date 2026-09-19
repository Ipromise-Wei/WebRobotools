<script setup lang="ts">
import DeviceStatus from '@/components/DeviceStatus.vue'
import SystemLog from '@/components/SystemLog.vue'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
</script>

<template>
  <div class="page"><div class="page-heading"><div><span class="eyebrow">SYSTEM OVERVIEW</span><h2>运行总览</h2></div><span class="mode-badge">{{ store.state.system.mode }} mode</span></div>
    <section class="hero"><div><span class="eyebrow">MISSION READY</span><h2>所有 Mock 设备<br />已进入待命状态</h2><p>当前链路用于验证控制、状态管理与实时通信。</p></div><div class="orbit"><span>3</span><small>DEVICES</small></div></section>
    <div class="device-grid">
      <DeviceStatus name="移动底盘" model="MINI V3" :connected="store.state.chassis.connected" :detail="store.state.chassis.moving ? '运动中' : '静止'" />
      <DeviceStatus name="机械臂" model="RML63 · 6 AXIS" :connected="store.state.arm.connected" :detail="store.state.arm.moving ? '运动中' : '静止'" accent="#79a7ff" />
      <DeviceStatus name="夹爪" model="AUTONOMOUS GRIPPER" :connected="store.state.gripper.connected" :detail="store.state.gripper.status" accent="#edb75b" />
    </div>
    <SystemLog :entries="['后端服务运行正常', '设备控制模式：Mock', store.socketConnected ? 'WebSocket 实时链路已建立' : '等待实时链路']" />
  </div>
</template>

