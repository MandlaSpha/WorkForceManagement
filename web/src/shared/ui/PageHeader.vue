<script setup lang="ts">
defineProps<{ eyebrow?: string; title: string; subtitle?: string }>()
</script>

<template>
  <header class="mb-6 mt-4 flex flex-wrap items-end justify-between gap-3">
    <div class="max-w-3xl">
      <p v-if="eyebrow" class="text-xs font-medium text-ink-muted">
        {{ eyebrow }}
      </p>
      <h1 class="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{{ title }}</h1>
      <p
        v-if="subtitle || $slots.subtitle"
        class="mt-2 max-w-2xl text-sm text-ink-muted sm:text-base"
      >
        <slot name="subtitle">{{ subtitle }}</slot>
      </p>
    </div>
    <div class="flex items-center gap-2"><slot name="actions" /></div>
  </header>
</template>
