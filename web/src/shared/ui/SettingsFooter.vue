<script setup lang="ts">
import AppButton from './AppButton.vue'

/** The bar under a settings card that saves as a whole: what state it is in, Discard, and the
 * submit button (the enclosing form's submit). Status is words, never colour alone. */
defineProps<{
  /** There are edits that have not been saved. */
  dirty: boolean
  /** Text shown while nothing is unsaved, e.g. "All changes saved". */
  cleanText: string
  submitLabel: string
  loading?: boolean
  disabled?: boolean
}>()
defineEmits<{ discard: [] }>()
</script>

<template>
  <div class="flex flex-wrap items-center justify-between gap-3">
    <p class="text-sm" :class="dirty ? 'font-medium text-warn' : 'text-ink-muted'" role="status">
      {{ dirty ? 'You have unsaved changes' : cleanText }}
    </p>
    <div class="flex items-center gap-2">
      <AppButton variant="ghost" :disabled="!dirty" @click="$emit('discard')">Discard</AppButton>
      <AppButton type="submit" :loading="loading" :disabled="disabled">{{ submitLabel }}</AppButton>
    </div>
  </div>
</template>
