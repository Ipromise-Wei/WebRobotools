<script setup lang="ts">
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
</script>
<template><div class="page"><div class="page-heading"><div><span class="eyebrow">DIAGNOSTICS</span><h2>系统状态</h2></div></div><section class="panel system-list"><div><span>Web 后端</span><strong :class="{ ok: store.state.system.backend }">{{ store.state.system.backend ? '运行中' : '离线' }}</strong></div><div><span>实时状态链路</span><strong :class="{ ok: store.socketConnected }">{{ store.socketConnected ? '已连接' : '重连中' }}</strong></div><div><span>ROS2</span><strong :class="{ ok: store.state.system.ros2 }">{{ store.state.system.ros2 ? '适配器已连接' : '等待数据' }}</strong></div><div><span>控制模式</span><strong>{{ store.state.system.mode.toUpperCase() }}</strong></div></section></div></template>
