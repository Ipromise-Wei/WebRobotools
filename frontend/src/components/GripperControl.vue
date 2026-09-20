<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { robotApi, type ArmConfig } from '@/api/robot'
import { useRobotStore } from '@/stores/robot'
const store = useRobotStore()
const config = ref<ArmConfig | null>(null)
const trueHardware = computed(() => store.state.system.mode === 'ros2')
const commandReady = computed(() => Boolean(trueHardware.value && config.value?.gripper_commands_enabled && store.state.gripper.connected))
const releaseReady = computed(() => Boolean(trueHardware.value && config.value?.gripper_enabled))

async function operate(action: 'open' | 'close' | 'stop') {
  if (action !== 'stop' && !window.confirm(`确定${action === 'open' ? '张开' : '闭合'}真机夹爪吗？`)) return
  await store.command(action === 'open' ? robotApi.openGripper : action === 'close' ? robotApi.closeGripper : robotApi.stopGripper)
}

onMounted(async () => {
  try { config.value = await robotApi.armConfig() }
  catch { config.value = null }
})
</script>

<template>
  <section class="panel gripper-control">
    <div class="gripper-visual" :class="store.state.gripper.status"><i></i><i></i><b></b></div>
    <h2>{{ store.state.gripper.status === 'opened' ? '夹爪已打开' : store.state.gripper.status === 'closed' ? '夹爪已闭合' : '夹爪已停止' }}</h2>
    <p>RML63 工具 IO · {{ commandReady ? '真机控制已解锁' : '真机控制锁定' }}</p>
    <div class="button-row"><button class="primary" :disabled="!commandReady || store.busy" @click="operate('open')">打开</button><button :disabled="!commandReady || store.busy" @click="operate('close')">关闭</button><button class="danger" :disabled="!releaseReady || store.busy" @click="operate('stop')">释放 IO</button></div>
  </section>
</template>
