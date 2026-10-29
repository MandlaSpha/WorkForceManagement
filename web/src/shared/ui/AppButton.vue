<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost'
    type?: 'button' | 'submit'
    loading?: boolean
    disabled?: boolean
    /** Id of the form this button submits, for a button that sits outside it (a dialog footer). */
    form?: string
  }>(),
  { variant: 'primary', type: 'button', loading: false, disabled: false, form: undefined },
)
</script>

<template>
  <button
    :type="type"
    :form="form"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="press inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60 sm:min-h-10"
    :class="{
      'bg-brand text-brand-contrast shadow-sm hover:-translate-y-px hover:shadow-md':
        variant === 'primary',
      'border border-line bg-surface text-ink hover:-translate-y-px hover:bg-surface-muted hover:shadow-sm':
        variant === 'secondary',
      'text-ink-muted hover:bg-surface-muted hover:text-ink': variant === 'ghost',
    }"
  >
    <slot />
  </button>
</template>
