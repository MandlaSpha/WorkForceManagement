<script setup lang="ts">
import { useId } from 'vue'

/** One soft rounded card of settings: an optional title with a status chip, then rows (put
 * `SettingsRow`s in the default slot), then an optional footer bar. */
defineProps<{ title?: string; description?: string }>()
const titleId = useId()
</script>

<template>
  <section
    class="overflow-hidden rounded-3xl bg-surface shadow-[var(--shadow-card)]"
    :aria-labelledby="title ? titleId : undefined"
  >
    <header
      v-if="title || $slots.status"
      class="flex flex-wrap items-center justify-between gap-2 px-5 pb-1 pt-5 sm:px-6"
    >
      <div>
        <h2 :id="titleId" class="text-lg font-semibold tracking-tight text-ink">{{ title }}</h2>
        <p v-if="description" class="mt-1 max-w-2xl text-sm text-ink-muted">{{ description }}</p>
      </div>
      <slot name="status" />
    </header>
    <div class="divide-y divide-line px-5 sm:px-6"><slot /></div>
    <footer v-if="$slots.footer" class="border-t border-line bg-surface-muted px-5 py-3 sm:px-6">
      <slot name="footer" />
    </footer>
  </section>
</template>
