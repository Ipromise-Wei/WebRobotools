<script setup lang="ts">
import ChassisControl from '@/components/ChassisControl.vue'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
</script>
<template><div class="page"><div class="page-heading"><div><span class="eyebrow">MINI V3</span><h2>移动底盘</h2></div><span class="mode-badge">{{ store.state.chassis.connected ? 'online' : 'offline' }}</span></div><div class="metrics"><article><small>线速度</small><strong>{{ store.state.chassis.linear_velocity.toFixed(2) }}</strong><span>m/s</span></article><article><small>角速度</small><strong>{{ store.state.chassis.angular_velocity.toFixed(2) }}</strong><span>rad/s</span></article><article><small>运动状态</small><strong class="text-metric">{{ store.state.chassis.moving ? '运动中' : '静止' }}</strong></article></div><ChassisControl /></div></template>

