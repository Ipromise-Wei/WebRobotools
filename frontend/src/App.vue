<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Login from '@/views/Login.vue'
import { useAuthStore } from '@/stores/auth'
import { useRobotStore } from '@/stores/robot'

const auth = useAuthStore()
const store = useRobotStore()
const route = useRoute()
const router = useRouter()

onBeforeUnmount(() => store.disconnect())

function safeLoginRedirect() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  return redirect.startsWith('/') && !redirect.startsWith('//') && redirect !== '/login'
    ? redirect
    : '/'
}

watch(
  () => [auth.ready, auth.authenticated] as const,
  ([ready, authenticated]) => {
    if (!ready) return
    if (authenticated) {
      void store.initialize()
      if (route.name === 'login') void router.replace(safeLoginRedirect())
      return
    }
    store.disconnect()
    if (route.name !== 'login') {
      const redirect = route.fullPath === '/' ? undefined : route.fullPath
      void router.replace({ name: 'login', query: redirect ? { redirect } : undefined })
    }
  },
  { immediate: true },
)

function signOut() {
  void auth.logout()
}
</script>

<template>
  <div v-if="!auth.ready" class="auth-loading" aria-live="polite">
    <span class="brand-mark">AI</span><p>正在验证安全会话…</p>
  </div>
  <Login v-else-if="!auth.authenticated || route.name === 'login'" />
  <div v-else class="app-shell">
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
        <div class="topbar-actions">
          <time>{{ new Date(store.state.updated_at).toLocaleString('zh-CN') }}</time>
          <span class="signed-user"><i></i>{{ auth.username }}</span>
          <button type="button" class="logout-button" @click="signOut">退出</button>
        </div>
      </header>
      <p v-if="store.error" class="alert">{{ store.error }}</p>
      <RouterView />
    </main>
  </div>
</template>
