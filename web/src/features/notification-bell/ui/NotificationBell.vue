<script setup lang="ts">
import { Bell } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useInbox } from '@/entities/notification'
import type { Notification } from '@/entities/notification'
import { formatDateTime } from '@/shared/lib/datetime'

import { useReadNotifications } from '../model/useReadNotifications'

const router = useRouter()
const inbox = useInbox()
const { readOne, readAll } = useReadNotifications()

const open = ref(false)
const unread = computed(() => inbox.data.value?.unread ?? 0)
const items = computed(() => inbox.data.value?.items ?? [])
const label = computed(() =>
  unread.value > 0 ? `Notifications, ${unread.value} unread` : 'Notifications',
)

function choose(n: Notification): void {
  if (!n.read) readOne.mutate(n.id)
  open.value = false
  if (n.link) void router.push(n.link)
}
</script>

<template>
  <div class="relative" role="presentation" @keydown.esc="open = false">
    <button
      type="button"
      class="relative inline-flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted hover:text-ink"
      :aria-label="label"
      :aria-expanded="open"
      aria-controls="notification-panel"
      @click="open = !open"
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

    <section
      v-if="open"
      id="notification-panel"
      class="absolute right-0 z-30 mt-2 w-80 max-w-[90vw] rounded-xl border border-line bg-surface shadow-lg"
      aria-label="Notifications"
    >
      <div class="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 class="text-sm font-semibold text-ink">Notifications</h2>
        <button
          v-if="unread > 0"
          type="button"
          class="text-xs font-medium text-brand-ink underline"
          @click="readAll.mutate()"
        >
          Mark all as read
        </button>
      </div>
      <p
        v-if="items.length === 0"
        class="px-3 py-4 text-sm text-ink-muted"
        data-testid="no-notifications"
      >
        You have no notifications.
      </p>
      <ul
        v-else
        class="max-h-96 divide-y divide-line overflow-y-auto"
        aria-label="Your notifications"
      >
        <li v-for="n in items" :key="n.id">
          <button
            type="button"
            class="block w-full px-3 py-2 text-left hover:bg-surface-muted"
            :data-testid="`notification-${n.id}`"
            @click="choose(n)"
          >
            <span class="block text-sm text-ink" :class="n.read ? '' : 'font-semibold'">
              <span v-if="!n.read" class="sr-only">Unread: </span>{{ n.message }}
            </span>
            <span class="block text-xs text-ink-muted">{{ formatDateTime(n.createdAt) }}</span>
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>
