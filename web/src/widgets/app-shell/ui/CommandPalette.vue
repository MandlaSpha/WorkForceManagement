<script setup lang="ts">
import { Search } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useQueues } from '@/entities/call-data'
import { useSessionStore } from '@/entities/session'
import { useContextStore } from '@/features/context-filters'
import Dialog from '@/shared/ui/Dialog.vue'

import { NAV_ICONS } from '../model/icons'
import { buildPalette, clampIndex, paletteOpen, type PaletteItem } from '../model/palette'
import { visibleNav } from '../model/visible-nav'

const session = useSessionStore()
const router = useRouter()
const context = useContextStore()

// The same cached query the top bar uses; roles without queues never ask.
const wantsQueues = computed(
  () =>
    session.user !== null &&
    session.user.role !== 'agent' &&
    session.user.features.includes('telephony'),
)
const queues = useQueues(wantsQueues)

// The typed text lives only in this component: it is filtered here and never sent anywhere.
const query = ref('')
const active = ref(0)
const input = ref<HTMLInputElement | null>(null)

const groups = computed(() =>
  session.user
    ? buildPalette({
        user: session.user,
        nav: visibleNav(session.user),
        queues: wantsQueues.value ? (queues.data.value ?? []) : [],
        query: query.value,
      })
    : [],
)
const flat = computed(() => groups.value.flatMap((g) => g.items))
const indexOf = (item: PaletteItem): number => flat.value.findIndex((i) => i.id === item.id)

watch(query, () => (active.value = 0))
watch(paletteOpen, (isOpen) => {
  if (isOpen) {
    query.value = ''
    active.value = 0
  }
})
watch(active, async () => {
  await nextTick()
  document
    .getElementById(optionId(flat.value[active.value]))
    ?.scrollIntoView?.({ block: 'nearest' })
})

function optionId(item: PaletteItem | undefined): string {
  return item ? `palette-opt-${item.id}` : ''
}

function choose(item: PaletteItem | undefined): void {
  if (!item) return
  if (item.kind === 'queue' && item.queueId !== undefined) context.queueId = String(item.queueId)
  paletteOpen.value = false
  void router.push(item.to)
}

function move(by: number): void {
  active.value = clampIndex(active.value + by, flat.value.length)
}

function onInputKey(e: KeyboardEvent): void {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    move(1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    move(-1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    choose(flat.value[active.value])
  }
}

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

// Ctrl+K / Cmd+K from anywhere; "/" only when you are not typing in a field.
function onKey(e: KeyboardEvent): void {
  if (!session.user) return
  const ctrlK = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k'
  const slash = e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !typing(e.target)
  if (!ctrlK && !slash) return
  e.preventDefault()
  paletteOpen.value = slash ? true : !paletteOpen.value
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  paletteOpen.value = false // it is module state: a new session must not start with it open
})
</script>

<template>
  <Dialog v-model:open="paletteOpen" title="Search" size="md" title-hidden>
    <div class="-mx-6 -my-5">
      <div class="flex items-center gap-3 border-b border-line px-5 py-3">
        <Search :size="18" class="text-ink-muted" aria-hidden="true" />
        <input
          ref="input"
          v-model="query"
          data-autofocus
          type="text"
          role="combobox"
          aria-label="Search pages, queues and actions"
          aria-controls="palette-list"
          aria-expanded="true"
          :aria-activedescendant="optionId(flat[active]) || undefined"
          autocomplete="off"
          spellcheck="false"
          placeholder="Search pages, queues and actions"
          class="h-10 w-full bg-transparent text-base text-ink placeholder:text-ink-muted focus:outline-none"
          @keydown="onInputKey"
        />
      </div>

      <div
        id="palette-list"
        role="listbox"
        aria-label="Results"
        class="quiet-scroll max-h-[50vh] overflow-y-auto p-2"
      >
        <p v-if="flat.length === 0" class="px-3 py-6 text-center text-sm text-ink-muted">
          Nothing matches "{{ query.trim() }}".
        </p>
        <div v-for="g in groups" :key="g.title" role="group" :aria-label="g.title" class="mb-1">
          <p
            class="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted"
            aria-hidden="true"
          >
            {{ g.title }}
          </p>
          <div
            v-for="item in g.items"
            :id="optionId(item)"
            :key="item.id"
            role="option"
            :aria-selected="indexOf(item) === active"
            class="flex min-h-12 cursor-pointer items-center gap-3 rounded-xl px-3 py-2"
            :class="
              indexOf(item) === active
                ? 'bg-brand-soft text-brand-ink'
                : 'text-ink hover:bg-surface-muted'
            "
            tabindex="-1"
            @mousemove="active = indexOf(item)"
            @click="choose(item)"
            @keydown.enter.prevent="choose(item)"
          >
            <span
              class="inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-ink-muted"
            >
              <component :is="NAV_ICONS[item.icon] ?? Search" :size="16" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-medium">{{ item.label }}</span>
              <span class="block truncate text-xs text-ink-muted">{{ item.hint }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
    <template #footer>
      <p class="mr-auto text-xs text-ink-muted">
        <kbd class="rounded border border-line px-1">&uarr;</kbd>
        <kbd class="ml-0.5 rounded border border-line px-1">&darr;</kbd> move
        <kbd class="ml-3 rounded border border-line px-1">Enter</kbd> open
        <kbd class="ml-3 rounded border border-line px-1">Esc</kbd> close
      </p>
    </template>
  </Dialog>
</template>
