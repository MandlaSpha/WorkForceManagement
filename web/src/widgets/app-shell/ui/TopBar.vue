<script setup lang="ts">
import { Menu } from 'lucide-vue-next'

import { ContextBar } from '@/features/context-filters'
import { NotificationBell } from '@/features/account/notifications'
import { ThemeToggle } from '@/features/toggle-theme'
import { useSessionStore } from '@/entities/session'

import BreadcrumbTrail from './BreadcrumbTrail.vue'

defineProps<{ menuOpen: boolean }>()
defineEmits<{ toggleMenu: [] }>()

const session = useSessionStore()
</script>

<template>
  <header class="flex flex-wrap items-end gap-x-4 gap-y-2 px-4 pb-2 pt-4 sm:px-6">
    <button
      type="button"
      class="inline-flex size-11 items-center justify-center rounded-xl bg-surface text-ink-muted shadow-[var(--shadow-card)] hover:text-ink lg:hidden"
      aria-label="Open navigation"
      aria-controls="sidebar"
      :aria-expanded="menuOpen"
      @click="$emit('toggleMenu')"
    >
      <Menu :size="18" aria-hidden="true" />
    </button>

    <BreadcrumbTrail />

    <!-- Agents work in their own week only; everyone else picks a site and queue too. -->
    <ContextBar :show-scope="session.user?.role !== 'agent'" />

    <div
      class="ml-auto flex items-center gap-1 rounded-2xl bg-surface px-1.5 py-1 shadow-[var(--shadow-card)]"
    >
      <NotificationBell />
      <ThemeToggle />
    </div>
  </header>
</template>
