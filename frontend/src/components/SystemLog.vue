<script setup lang="ts">
defineProps<{ entries: string[] }>()
</script>
<template><section class="panel log"><div class="section-title"><h2>系统事件</h2><span>LIVE</span></div><p v-for="entry in entries" :key="entry"><time>NOW</time>{{ entry }}</p></section></template>

