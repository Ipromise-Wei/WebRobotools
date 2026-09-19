<script setup lang="ts">
defineProps<{ name: string; model: string; connected: boolean; detail: string; accent?: string }>()
</script>

<template>
  <article class="device-card" :style="{ '--accent': accent || '#37d6c0' }">
    <div class="device-card__head"><span class="device-icon">{{ name.slice(0, 1) }}</span><span class="status-dot" :class="{ online: connected }"></span></div>
    <p>{{ model }}</p><h3>{{ name }}</h3><small>{{ connected ? 'ONLINE' : 'OFFLINE' }} · {{ detail }}</small>
  </article>
</template>

