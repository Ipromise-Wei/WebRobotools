<script setup lang="ts">
import { ref } from 'vue'
import { robotApi } from '@/api/robot'
import { useRobotStore } from '@/stores/robot'

const store = useRobotStore()
const linear = ref(0.3)
const angular = ref(0.8)
const move = (l: number, a: number) => store.command(() => robotApi.moveChassis(l, a))
</script>

<template>
  <div class="control-panel">
    <div class="dpad">
      <button class="up" :disabled="store.busy" @click="move(linear, 0)">↑<span>前进</span></button>
      <button class="left" :disabled="store.busy" @click="move(0, angular)">↶<span>左转</span></button>
      <button class="stop" :disabled="store.busy" @click="store.command(robotApi.stopChassis)">■<span>停止</span></button>
      <button class="right" :disabled="store.busy" @click="move(0, -angular)">↷<span>右转</span></button>
      <button class="down" :disabled="store.busy" @click="move(-linear, 0)">↓<span>后退</span></button>
    </div>
    <div class="settings">
      <label>线速度 <output>{{ linear.toFixed(1) }} m/s</output><input v-model.number="linear" type="range" min="0.1" max="1" step="0.1" /></label>
      <label>角速度 <output>{{ angular.toFixed(1) }} rad/s</output><input v-model.number="angular" type="range" min="0.1" max="2" step="0.1" /></label>
    </div>
  </div>
</template>

