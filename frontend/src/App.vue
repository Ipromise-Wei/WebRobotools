<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRobotStore } from '@/stores/robot'

const store = useRobotStore()

onMounted(() => {
  void store.initialize()
})
onBeforeUnmount(() => store.disconnect())
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">AI</span>
        <div><strong>HZAU@AIOT</strong><small>农业AI机器人协同平台</small></div>
      </div>
      <nav>
        <RouterLink to="/">总览</RouterLink>
        <RouterLink to="/chassis">移动底盘</RouterLink>
        <RouterLink to="/arm">机械臂</RouterLink>
        <RouterLink to="/gripper">夹爪</RouterLink>
        <RouterLink to="/system">系统</RouterLink>
      </nav>
      <div class="connection-pill" :class="{ online: store.socketConnected }">
        <span></span>{{ store.socketConnected ? '实时链路在线' : '正在连接' }}
      </div>
    </aside>
    <main>
      <header class="topbar">
        <div><span class="eyebrow">{{ store.state.system.mode.toUpperCase() }} · ROBOT COLLABORATION</span><h1>HZAU@AIOT农业AI机器人协同工作平台</h1></div>
        <time>{{ new Date(store.state.updated_at).toLocaleString('zh-CN') }}</time>
      </header>
      <p v-if="store.error" class="alert">{{ store.error }}</p>
      <RouterView />
    </main>
  </div>
</template>
