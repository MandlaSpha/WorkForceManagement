<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'info' | 'warn' | 'danger' }>(), { tone: 'info' })
</script>

<template>
  <div
    :role="tone === 'info' ? 'status' : 'alert'"
    class="rounded-xl border px-4 py-3 text-sm"
    :class="{
      'border-line bg-surface text-ink-muted': tone === 'info',
      'border-warn/40 bg-warn-soft text-warn': tone === 'warn',
      'border-danger/40 bg-danger-soft text-danger': tone === 'danger',
    }"
  >
    <slot />
  </div>
</template>
