<script setup lang="ts">
import { KeyRound } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { ROLE_LABELS, useSessionStore } from '@/entities/session'
import { SignOutButton } from '@/features/sign-out'

const session = useSessionStore()
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)

const initials = computed(() =>
  (session.user?.displayName ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join(''),
)

function close(returnFocus = false): void {
  open.value = false
  if (returnFocus) trigger.value?.focus()
}

function onDocumentClick(event: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(event.target as Node)) close()
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) close(true)
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div v-if="session.user" ref="root" class="relative pl-2">
    <button
      ref="trigger"
      type="button"
      class="flex items-center gap-2 rounded-lg p-1 hover:bg-surface-muted"
      aria-haspopup="menu"
      :aria-expanded="open"
      aria-controls="account-menu"
      :aria-label="`Account menu for ${session.user.displayName}`"
      @click="open = !open"
    >
      <span
        class="inline-flex size-8 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand-ink"
        aria-hidden="true"
      >
        {{ initials }}
      </span>
      <span class="hidden text-left leading-tight sm:block">
        <span class="block text-sm font-medium text-ink">{{ session.user.displayName }}</span>
        <span class="block text-xs text-ink-muted">{{ ROLE_LABELS[session.user.role] }}</span>
      </span>
    </button>

    <div
      v-if="open"
      id="account-menu"
      role="menu"
      aria-label="Account"
      class="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-line bg-surface p-1 shadow-lg"
    >
      <p class="px-3 py-2 text-xs text-ink-muted">
        Signed in as <span class="font-medium text-ink">{{ session.user.displayName }}</span>
      </p>
      <RouterLink
        to="/change-password"
        role="menuitem"
        class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink hover:bg-surface-muted"
        @click="close()"
      >
        <KeyRound :size="16" aria-hidden="true" />
        Change password
      </RouterLink>
      <div role="none" class="border-t border-line pt-1 mt-1">
        <SignOutButton class="w-full justify-start" role="menuitem" />
      </div>
    </div>
  </div>
</template>
