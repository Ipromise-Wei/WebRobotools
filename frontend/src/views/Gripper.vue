<script setup lang="ts">
import GripperControl from '@/components/GripperControl.vue'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
</script>
<template><div class="page"><div class="page-heading"><div><span class="eyebrow">END EFFECTOR</span><h2>夹爪</h2></div><span class="mode-badge">{{ store.state.gripper.connected ? 'online' : 'offline' }}</span></div><GripperControl /></div></template>

