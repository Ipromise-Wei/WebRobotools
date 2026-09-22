<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const username = ref('admin')
const password = ref('')
const showPassword = ref(false)

async function submit() {
  const succeeded = await auth.login(username.value, password.value)
  if (!succeeded) password.value = ''
}
</script>

<template>
  <main class="login-page">
    <section class="login-context" aria-label="平台介绍">
      <div class="login-brand">
        <span class="brand-mark">AI</span>
        <div><strong>HZAU@AIOT</strong><small>农业AI机器人协同工作平台</small></div>
      </div>
      <div class="field-illustration" aria-hidden="true">
        <div class="field-sun"></div>
        <div class="field-lines"><i></i><i></i><i></i><i></i><i></i></div>
        <div class="field-robot"><b>R</b><span></span></div>
      </div>
      <div class="login-intro">
        <span>ROBOT OPERATIONS</span>
        <h1>农业机器人<br>协同控制中心</h1>
        <p>统一管理移动底盘、机械臂、视觉设备与 ROS2 作业模块。</p>
      </div>
      <footer>HZAU · AIOT LAB</footer>
    </section>

    <section class="login-form-area">
      <form class="login-card" @submit.prevent="submit">
        <header>
          <span class="login-kicker">AUTHORIZED ACCESS</span>
          <h2>登录工作平台</h2>
          <p>使用管理员账户进入真机控制系统</p>
        </header>

        <p v-if="auth.error" class="login-error" role="alert">{{ auth.error }}</p>

        <label>
          <span>用户名</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            maxlength="64"
            required
            autofocus
            placeholder="请输入用户名"
          >
        </label>
        <label>
          <span>密码</span>
          <div class="password-field">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              name="password"
              autocomplete="current-password"
              maxlength="256"
              required
              placeholder="请输入密码"
            >
            <button type="button" @click="showPassword = !showPassword">
              {{ showPassword ? '隐藏' : '显示' }}
            </button>
          </div>
        </label>

        <button class="login-submit" type="submit" :disabled="auth.loading">
          {{ auth.loading ? '正在验证…' : '安全登录' }}
        </button>
        <div class="login-help">
          <b>安全提示</b>
          <p>本平台可直接控制真机，仅限已授权人员使用。首次启动密码会显示在后端终端中。</p>
        </div>
      </form>
    </section>
  </main>
</template>
