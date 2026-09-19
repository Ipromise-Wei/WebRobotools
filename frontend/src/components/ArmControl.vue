<script setup lang="ts">
import { reactive, watch } from 'vue'
import { robotApi } from '@/api/robot'
import { useRobotStore, type Pose } from '@/stores/robot'

const store = useRobotStore()
const joints = reactive([...store.state.arm.joints])
const pose = reactive<Pose>({ ...store.state.arm.pose })
watch(() => store.state.arm.joints, (value) => value.forEach((item, index) => joints[index] = item))
</script>

<template>
  <div class="split-control">
    <section class="panel"><div class="section-title"><h2>关节控制</h2><span>DEG</span></div>
      <label v-for="(_, index) in joints" :key="index" class="joint-row">
        <strong>J{{ index + 1 }}</strong><input v-model.number="joints[index]" type="range" min="-180" max="180" step="1" /><output>{{ joints[index].toFixed(0) }}°</output>
      </label>
      <button class="primary wide" :disabled="store.busy" @click="store.command(() => robotApi.moveJoints([...joints]))">执行关节运动</button>
    </section>
    <section class="panel"><div class="section-title"><h2>末端位姿</h2><span>MOCK</span></div>
      <div class="pose-grid"><label v-for="key in (Object.keys(pose) as (keyof Pose)[])" :key="key">{{ key.toUpperCase() }}<input v-model.number="pose[key]" type="number" step="0.1" /></label></div>
      <div class="button-row"><button class="primary" :disabled="store.busy" @click="store.command(() => robotApi.movePose({ ...pose }))">移动至位姿</button><button class="danger" :disabled="store.busy" @click="store.command(robotApi.stopArm)">停止</button></div>
    </section>
  </div>
</template>

