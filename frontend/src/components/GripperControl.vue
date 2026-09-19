<script setup lang="ts">
import { robotApi } from '@/api/robot'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
</script>

<template>
  <section class="panel gripper-control">
    <div class="gripper-visual" :class="store.state.gripper.status"><i></i><i></i><b></b></div>
    <h2>{{ store.state.gripper.status === 'opened' ? '夹爪已打开' : store.state.gripper.status === 'closed' ? '夹爪已闭合' : '夹爪已停止' }}</h2>
    <p>当前位置 {{ Math.round(store.state.gripper.position * 100) }}%</p>
    <div class="button-row"><button class="primary" :disabled="store.busy" @click="store.command(robotApi.openGripper)">打开</button><button :disabled="store.busy" @click="store.command(robotApi.closeGripper)">关闭</button><button class="danger" :disabled="store.busy" @click="store.command(robotApi.stopGripper)">停止</button></div>
  </section>
</template>

