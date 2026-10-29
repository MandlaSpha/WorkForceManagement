<script setup lang="ts">
import { ArrowLeftRight, Bell, Calendar, Clock } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, type Component } from 'vue'
import { useRouter } from 'vue-router'

import { useInbox } from '@/entities/notification'
import type { Notification } from '@/entities/notification'
import { relativeTime } from '@/shared/lib/datetime'

import { useReadNotifications } from '../model/useReadNotifications'

const router = useRouter()
const inbox = useInbox()
const { readOne, readAll } = useReadNotifications()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const list = ref<HTMLElement | null>(null)
const unread = computed(() => inbox.data.value?.unread ?? 0)
const items = computed(() => inbox.data.value?.items ?? [])
const label = computed(() =>
  unread.value > 0 ? `Notifications, ${unread.value} unread` : 'Notifications',
)
const now = ref(new Date())

/** A round icon by what the notice is about; anything unknown gets the bell. */
function iconFor(kind: string): Component {
  if (kind.startsWith('leave')) return Calendar
  if (kind.startsWith('swap')) return ArrowLeftRight
  if (kind.startsWith('overtime')) return Clock
  return Bell
}

async function toggle(): Promise<void> {
  open.value = !open.value
  if (open.value) {
    now.value = new Date()
    await nextTick()
    rows()[0]?.focus()
  }
}

function close(returnFocus = true): void {
  if (!open.value) return
  open.value = false
  if (returnFocus) trigger.value?.focus()
}

function choose(n: Notification): void {
  if (!n.read) readOne.mutate(n.id)
  close(false)
  if (n.link) void router.push(n.link)
}

function rows(): HTMLElement[] {
  return Array.from(list.value?.querySelectorAll<HTMLElement>('button[data-row]') ?? [])
}

// Up and Down move between notices; Home and End jump to the ends.
function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    close()
    return
  }
  const all = rows()
  const at = all.indexOf(document.activeElement as HTMLElement)
  let next = -1
  if (e.key === 'ArrowDown') next = Math.min(at + 1, all.length - 1)
  else if (e.key === 'ArrowUp') next = Math.max(at - 1, 0)
  else if (e.key === 'Home') next = 0
  else if (e.key === 'End') next = all.length - 1
  if (next < 0) return
  e.preventDefault()
  all[next]?.focus()
}

function onOutside(e: MouseEvent): void {
  if (open.value && root.value && !root.value.contains(e.target as Node)) close(false)
}
onMounted(() => document.addEventListener('mousedown', onOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onOutside))
</script>

<template>
  <div ref="root" class="relative" role="presentation" @keydown="onKeydown">
    <button
      ref="trigger"
      type="button"
      class="relative inline-flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted hover:text-ink"
      :aria-label="label"
      :aria-expanded="open"
      aria-controls="notification-panel"
      @click="toggle"
    >
      <Bell :size="18" aria-hidden="true" />
      <span
        v-if="unread > 0"
        class="absolute -right-0.5 -top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-4 text-white"
        data-testid="unread-count"
        aria-hidden="true"
      >
        {{ unread > 9 ? '9+' : unread }}
      </span>
    </button>
    <!-- Announces a change in the count to a screen reader without moving focus. -->
    <span class="sr-only" aria-live="polite" data-testid="unread-live">{{
      unread > 0 ? `${unread} unread notifications` : 'No unread notifications'
    }}</span>

    <section
      v-if="open"
      id="notification-panel"
      class="absolute right-0 z-30 mt-3 w-96 max-w-[92vw] overflow-hidden rounded-3xl border border-line bg-surface shadow-[var(--shadow-pop)]"
      aria-label="Notifications"
    >
      <div class="flex items-center justify-between px-5 pb-2 pt-4">
        <h2 class="text-base font-semibold text-ink">Notifications</h2>
        <button
          v-if="unread > 0"
          type="button"
          class="rounded-lg px-2 py-1 text-xs font-semibold text-brand-ink hover:bg-brand-soft"
          @click="readAll.mutate()"
        >
          Mark all as read
        </button>
      </div>
      <p
        v-if="items.length === 0"
        class="px-5 pb-6 pt-3 text-center text-sm text-ink-muted"
        data-testid="no-notifications"
      >
        You have no notifications.
      </p>
      <ul
        v-else
        ref="list"
        class="max-h-96 space-y-0.5 overflow-y-auto px-2 pb-2"
        aria-label="Your notifications"
      >
        <li v-for="n in items" :key="n.id">
          <button
            type="button"
            data-row
            class="flex w-full items-start gap-3 rounded-2xl px-3 py-2.5 text-left hover:bg-surface-muted focus-visible:bg-surface-muted"
            :data-testid="`notification-${n.id}`"
            @click="choose(n)"
          >
            <span
              class="mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-full"
              :class="n.read ? 'bg-surface-muted text-ink-muted' : 'bg-brand-soft text-brand-ink'"
            >
              <component :is="iconFor(n.kind)" :size="16" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block text-sm text-ink" :class="n.read ? '' : 'font-semibold'">
                <span v-if="!n.read" class="sr-only">Unread: </span>{{ n.message }}
              </span>
              <span class="block text-xs text-ink-muted">{{ relativeTime(n.createdAt, now) }}</span>
            </span>
            <span
              v-if="!n.read"
              class="mt-2 size-2 shrink-0 rounded-full bg-brand"
              aria-hidden="true"
            />
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
