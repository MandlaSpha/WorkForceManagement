<script setup lang="ts">
import { Ellipsis, KeyRound } from 'lucide-vue-next'
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
  <div v-if="session.user" ref="root" class="relative">
    <button
      ref="trigger"
      type="button"
      class="flex min-h-14 w-full items-center gap-3 rounded-2xl bg-side-hover p-2 text-left hover:bg-side-line"
      aria-haspopup="menu"
      :aria-expanded="open"
      aria-controls="account-menu"
      :aria-label="`Account menu for ${session.user.displayName}`"
      @click="open = !open"
    >
      <span
        class="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-side-pill text-xs font-semibold text-on-side-pill ring-2 ring-side-line ring-offset-2 ring-offset-side"
        aria-hidden="true"
      >
        {{ initials }}
      </span>
      <span class="min-w-0 flex-1 leading-tight">
        <span class="block truncate text-sm font-semibold text-on-side">{{
          session.user.displayName
        }}</span>
        <span class="block truncate text-xs text-side-dim">{{
          ROLE_LABELS[session.user.role]
        }}</span>
      </span>
      <Ellipsis :size="18" class="shrink-0 text-side-dim" aria-hidden="true" />
    </button>

    <div
      v-if="open"
      id="account-menu"
      role="menu"
      aria-label="Account"
      class="absolute inset-x-0 bottom-full z-50 mb-2 rounded-2xl border border-line bg-surface p-1 text-ink shadow-[var(--shadow-pop)]"
    >
      <p class="px-3 py-2 text-xs text-ink-muted">
        Signed in as <span class="font-medium text-ink">{{ session.user.displayName }}</span>
      </p>
      <RouterLink
        to="/change-password"
        role="menuitem"
        class="flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm text-ink hover:bg-surface-muted"
        @click="close()"
      >
        <KeyRound :size="16" aria-hidden="true" />
        Change password
      </RouterLink>
      <div role="none" class="mt-1 border-t border-line pt-1">
        <SignOutButton class="w-full justify-start" role="menuitem" />
      </div>
    </div>
  </div>
</template>
