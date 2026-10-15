<script setup lang="ts">
import { Menu } from 'lucide-vue-next'
import { computed } from 'vue'

import { ContextBar } from '@/features/context-filters'
import { NotificationBell } from '@/features/notification-bell'
import { SignOutButton } from '@/features/sign-out'
import { ThemeToggle } from '@/features/toggle-theme'
import { ROLE_LABELS, useSessionStore } from '@/entities/session'

defineProps<{ menuOpen: boolean }>()
defineEmits<{ toggleMenu: [] }>()

const session = useSessionStore()
const initials = computed(() =>
  (session.user?.displayName ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join(''),
)
</script>

<template>
  <header
    class="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-line bg-surface px-4 py-2 sm:px-6"
  >
    <button
      type="button"
      class="inline-flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted lg:hidden"
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
      <div v-if="session.user" class="flex items-center gap-2 pl-2">
        <span
          class="inline-flex size-8 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-ink"
          aria-hidden="true"
        >
          {{ initials }}
        </span>
        <div class="hidden text-left leading-tight sm:block">
          <p class="text-sm font-medium text-ink">{{ session.user.displayName }}</p>
          <p class="text-xs text-ink-muted">{{ ROLE_LABELS[session.user.role] }}</p>
        </div>
        <SignOutButton />
      </div>
    </div>
  </header>
</template>
