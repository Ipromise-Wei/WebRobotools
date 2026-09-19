<script setup lang="ts">
import { ref } from 'vue'
defineProps<{ url: string }>()
const failed = ref(false)
</script>
<template><section class="panel camera-panel"><div class="section-title"><h2>实时摄像头</h2><span>{{ url && !failed ? 'LIVE' : 'WAITING' }}</span></div><div class="visual-stage"><img v-if="url && !failed" :src="url" alt="机器人摄像头" @error="failed = true" /><div v-else class="visual-empty"><b>CAM</b><p>尚未配置视频流</p><small>等待相机功能包与 Web 视频接口</small></div></div></section></template>
