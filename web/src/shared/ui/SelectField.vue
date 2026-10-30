<script setup lang="ts">
import { useId } from 'vue'

const model = defineModel<string>({ required: true })

defineProps<{
  label: string
  options: ReadonlyArray<{ value: string; label: string }>
  disabled?: boolean
  /** Shown when there are no options yet (honest empty state, not a blank box). */
  emptyText?: string
  /** The label stays for screen readers but is not drawn: a settings row already shows it. */
  hideLabel?: boolean
}>()

const id = useId()
</script>

<template>
  <div class="min-w-0">
    <label
      :for="id"
      class="block text-xs font-medium text-ink-muted"
      :class="{ 'sr-only': hideLabel }"
    >
      {{ label }}
    </label>
    <select
      :id="id"
      v-model="model"
      :disabled="disabled || options.length === 0"
      class="block min-h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink disabled:opacity-60"
    >
      <option v-if="options.length === 0" value="">{{ emptyText ?? 'None available' }}</option>
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </div>
</template>
