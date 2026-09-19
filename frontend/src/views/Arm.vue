<script setup lang="ts">
import ArmControl from '@/components/ArmControl.vue'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
</script>
<template><div class="page"><div class="page-heading"><div><span class="eyebrow">RML63 · 6 DOF</span><h2>机械臂</h2></div><span class="mode-badge">{{ store.state.arm.moving ? 'moving' : 'idle' }}</span></div><ArmControl /></div></template>

