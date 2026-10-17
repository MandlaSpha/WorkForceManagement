<script setup lang="ts">
import { Menu } from 'lucide-vue-next'

import { ContextBar } from '@/features/context-filters'
import { NotificationBell } from '@/features/account/notifications'
import { ThemeToggle } from '@/features/toggle-theme'
import { useSessionStore } from '@/entities/session'

import AccountMenu from './AccountMenu.vue'

defineProps<{ menuOpen: boolean }>()
defineEmits<{ toggleMenu: [] }>()

const session = useSessionStore()
</script>

<template>
  <header
    class="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-line bg-surface px-4 py-2 sm:px-6"
  >
    <button
      type="button"
      class="inline-flex size-11 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted lg:hidden"
      aria-label="Open navigation"
      aria-controls="sidebar"
      :aria-expanded="menuOpen"
      @click="$emit('toggleMenu')"
    >
      <Menu :size="18" aria-hidden="true" />
    </button>

    <!-- Agents work in their own week only; everyone else picks a site and queue too. -->
    <ContextBar :show-scope="session.user?.role !== 'agent'" />

    <div class="ml-auto flex items-center gap-1">
      <NotificationBell />
      <ThemeToggle />
      <AccountMenu />
    </div>
  </header>
</template>
