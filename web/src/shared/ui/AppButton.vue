<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost'
    type?: 'button' | 'submit'
    loading?: boolean
    disabled?: boolean
  }>(),
  { variant: 'primary', type: 'button', loading: false, disabled: false },
)
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="inline-flex min-h-11 items-center sm:min-h-10 justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60"
    :class="{
      'bg-brand text-brand-contrast hover:opacity-90': variant === 'primary',
      'border border-line bg-surface text-ink hover:bg-surface-muted': variant === 'secondary',
      'text-ink-muted hover:bg-surface-muted hover:text-ink': variant === 'ghost',
    }"
  >
    <slot />
  </button>
</template>
