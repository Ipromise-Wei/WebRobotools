<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ url: string; connected?: boolean; error?: string }>()
const failed = ref(false)
watch(() => [props.url, props.connected], () => { if (props.url) failed.value = false })
</script>
<template><section class="panel camera-panel"><div class="section-title"><h2>RealSense 实时画面</h2><span>{{ connected && !failed ? 'LIVE' : 'WAITING' }}</span></div><div class="visual-stage"><img v-if="url && !failed" :src="url" alt="RealSense 彩色画面" @load="failed = false" @error="failed = true" /><div v-if="!url || failed || !connected" class="visual-empty camera-waiting"><b>RS</b><p>{{ error || (url ? '正在连接 RealSense' : 'RealSense 视频流未启用') }}</p><small>仅显示真实相机画面，不生成模拟视频</small></div></div></section></template>
