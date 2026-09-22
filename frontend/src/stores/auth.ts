import axios from 'axios'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const ready = ref(false)
  const loading = ref(false)
  const authenticated = ref(false)
  const enabled = ref(true)
  const username = ref('')
  const expiresAt = ref<number | null>(null)
  const error = ref('')

  const sessionExpiresAt = computed(() => (
    expiresAt.value ? new Date(expiresAt.value * 1000) : null
  ))

  function applyStatus(status: Awaited<ReturnType<typeof authApi.status>>) {
    enabled.value = status.enabled
    authenticated.value = status.authenticated
    username.value = status.username
    expiresAt.value = status.expires_at
  }

  function expireSession(message = '登录已过期，请重新登录。') {
    authenticated.value = false
    username.value = ''
    expiresAt.value = null
    ready.value = true
    error.value = message
  }

  async function initialize() {
    loading.value = true
    error.value = ''
    try {
      applyStatus(await authApi.status())
    }
    catch {
      expireSession('无法连接认证服务，请确认后端已经启动。')
    }
    finally {
      loading.value = false
      ready.value = true
    }
  }

  async function login(loginUsername: string, password: string) {
    loading.value = true
    error.value = ''
    try {
      applyStatus(await authApi.login(loginUsername.trim(), password))
      return authenticated.value
    }
    catch (reason) {
      if (axios.isAxiosError(reason)) {
        if (!reason.response) error.value = '无法连接服务器，请检查后端服务和网络。'
        else error.value = String(reason.response.data?.detail || '登录失败，请重试。')
      }
      else error.value = reason instanceof Error ? reason.message : '登录失败，请重试。'
      return false
    }
    finally { loading.value = false }
  }

  async function logout() {
    loading.value = true
    try { await authApi.logout() }
    catch { /* Local sign-out still proceeds if the backend is unavailable. */ }
    finally {
      authenticated.value = false
      username.value = ''
      expiresAt.value = null
      error.value = ''
      loading.value = false
    }
  }

  window.addEventListener('webrobot:session-expired', () => expireSession())

  return {
    ready,
    loading,
    authenticated,
    enabled,
    username,
    sessionExpiresAt,
    error,
    initialize,
    login,
    logout,
    expireSession,
  }
})
