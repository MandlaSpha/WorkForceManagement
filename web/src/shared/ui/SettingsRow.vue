<script setup lang="ts">
/** A setting: bold label and one line of helper text on the left, the control on the right. On a
 * phone the control drops below the text so neither is squeezed. The control must carry its own
 * accessible name (for example `TextField` with `hide-label`); the drawn label is a caption. */
defineProps<{ label: string; helper?: string }>()
</script>

<template>
  <div class="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
    <div class="min-w-0 sm:max-w-md">
      <p class="text-sm font-semibold text-ink">{{ label }}</p>
      <p v-if="helper" class="mt-0.5 text-sm text-ink-muted">{{ helper }}</p>
    </div>
    <div class="w-full shrink-0 sm:w-56"><slot /></div>
  </div>
</template>
