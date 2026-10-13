<script setup lang="ts">
import { useId } from 'vue'

const model = defineModel<string>({ required: true })

defineProps<{
  label: string
  type?: 'text' | 'password' | 'date'
  autocomplete?: string
  error?: string
}>()

const id = useId()
</script>

<template>
  <div class="space-y-1">
    <label :for="id" class="block text-xs font-medium text-ink-muted">{{ label }}</label>
    <input
      :id="id"
      v-model="model"
      :type="type ?? 'text'"
      :autocomplete="autocomplete"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? `${id}-error` : undefined"
      class="block min-h-10 w-full rounded-lg border bg-surface px-3 text-sm text-ink"
      :class="error ? 'border-danger' : 'border-line'"
    />
    <p v-if="error" :id="`${id}-error`" class="text-xs text-danger">{{ error }}</p>
  </div>
</template>
