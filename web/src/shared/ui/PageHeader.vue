<script setup lang="ts">
defineProps<{ eyebrow?: string; title: string; subtitle?: string }>()
</script>

<template>
  <header class="mb-6 flex flex-wrap items-start justify-between gap-3">
    <div class="max-w-3xl">
      <p v-if="eyebrow" class="text-[11px] font-semibold uppercase tracking-wide text-brand-ink">
        {{ eyebrow }}
      </p>
      <h1 class="text-xl font-semibold text-ink">{{ title }}</h1>
      <p v-if="subtitle" class="mt-1 text-sm text-ink-muted">{{ subtitle }}</p>
    </div>
    <div class="flex items-center gap-2"><slot name="actions" /></div>
  </header>
</template>
