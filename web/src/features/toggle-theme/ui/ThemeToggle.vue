<script setup lang="ts">
import { Moon, Sun } from 'lucide-vue-next'

import { useThemeStore } from '../model/theme'

const theme = useThemeStore()
</script>

<template>
  <button
    type="button"
    class="inline-flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted hover:text-ink"
    :aria-label="theme.dark ? 'Switch to light mode' : 'Switch to dark mode'"
    :aria-pressed="theme.dark"
    @click="theme.toggle()"
  >
    <Sun v-if="theme.dark" :size="18" aria-hidden="true" />
    <Moon v-else :size="18" aria-hidden="true" />
  </button>
</template>
