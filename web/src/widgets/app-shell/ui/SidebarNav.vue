<script setup lang="ts">
import { ChevronRight, Search } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import type { NavGroup } from '@/shared/config'
import BrandMark from '@/shared/ui/BrandMark.vue'

import { isActivePath } from '../model/active'
import { NAV_ICONS } from '../model/icons'
import {
  activeGroup,
  afterClick,
  findScreens,
  NAV_OPEN_KEY,
  openGroups,
  parseRemembered,
} from '../model/nav-state'
import { visibleNav } from '../model/visible-nav'

const session = useSessionStore()
const route = useRoute()
const router = useRouter()
const groups = computed(() => (session.user ? visibleNav(session.user) : []))

// Groups the person opened; the group you are in is always open on top of these.
function recall(): string[] {
  try {
    return parseRemembered(localStorage.getItem(NAV_OPEN_KEY))
  } catch {
    return [] // storage can be blocked; the menu then simply starts closed
  }
}
const remembered = ref<string[]>(recall())
const open = computed(() => openGroups(groups.value, route.path, remembered.value))

/** An id the page can point at: group names have spaces ("My work"), ids may not. */
const groupId = (group: string): string => `nav-${group.toLowerCase().replace(/\s+/g, '-')}`

function toggle(group: NavGroup): void {
  const next = afterClick(open.value, group)
  remembered.value = next
  save(next)
}

function save(value: string[]): void {
  try {
    localStorage.setItem(NAV_OPEN_KEY, JSON.stringify(value))
  } catch {
    /* not remembered; still works for this visit */
  }
}

// Going to a screen in a group that is closed (a link in a page, the finder, back/forward) opens
// that group and closes the rest, so you always see where you are.
watch(
  () => route.path,
  (path) => {
    const here = activeGroup(groups.value, path)
    if (here && !open.value.has(here)) {
      remembered.value = [here]
      save([here])
    }
  },
)

const query = ref('')
const results = computed(() => findScreens(groups.value, query.value))
const finder = ref<HTMLInputElement | null>(null)

function go(path: string): void {
  query.value = ''
  void router.push(path)
}
function firstResult(): void {
  const first = results.value[0]
  if (first) go(first.path)
}

// Ctrl+K (or Cmd+K) jumps to the finder from anywhere.
function onKey(e: KeyboardEvent): void {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    finder.value?.focus()
    finder.value?.select()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="px-5 pb-3 pt-5">
      <BrandMark />
      <p class="mt-2.5 text-sm font-semibold text-on-side">Workforce Management</p>
    </div>

    <div class="px-4 pb-2">
      <label class="sr-only" for="screen-finder">Find a screen</label>
      <div class="relative">
        <Search
          :size="14"
          class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-side-faint"
          aria-hidden="true"
        />
        <input
          id="screen-finder"
          ref="finder"
          v-model="query"
          type="search"
          autocomplete="off"
          placeholder="Find a screen"
          class="h-10 w-full rounded-xl border border-side-line bg-side-hover pl-9 pr-12 text-sm text-on-side placeholder:text-side-faint"
          @keydown.enter.prevent="firstResult"
          @keydown.esc="query = ''"
        />
        <kbd
          class="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded-md border border-side-line px-1.5 text-[10px] text-side-faint lg:block"
          aria-hidden="true"
          >Ctrl K</kbd
        >
      </div>
    </div>

    <nav aria-label="Main navigation" class="quiet-scroll flex-1 overflow-y-auto px-3 pb-4">
      <ul v-if="query.trim()" class="mt-1 space-y-0.5" aria-label="Matching screens">
        <li v-for="m in results" :key="m.key">
          <RouterLink
            :to="m.path"
            class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm text-side-dim hover:bg-side-hover hover:text-on-side lg:min-h-10"
            @click="query = ''"
          >
            <component :is="NAV_ICONS[m.icon]" :size="16" aria-hidden="true" />
            <span class="flex-1">{{ m.label }}</span>
            <span class="text-[10px] uppercase tracking-wider">{{ m.group }}</span>
          </RouterLink>
        </li>
        <li v-if="results.length === 0" class="px-2 py-2 text-sm text-side-dim">
          No screen matches "{{ query.trim() }}".
        </li>
      </ul>

      <template v-else>
        <section v-for="g in groups" :key="g.group" class="mt-1">
          <h2>
            <button
              type="button"
              class="mt-2 flex min-h-9 w-full items-center gap-1 rounded-xl px-3 text-[11px] font-semibold uppercase tracking-wider text-side-faint hover:text-on-side"
              :aria-expanded="open.has(g.group)"
              :aria-controls="groupId(g.group)"
              @click="toggle(g.group)"
            >
              <ChevronRight
                :size="14"
                class="transition-transform"
                :class="open.has(g.group) ? 'rotate-90' : ''"
                aria-hidden="true"
              />
              <span class="flex-1 text-left">{{ g.group }}</span>
              <span class="font-normal normal-case tracking-normal">{{ g.items.length }}</span>
            </button>
          </h2>
          <ul v-show="open.has(g.group)" :id="groupId(g.group)" class="mt-0.5 space-y-0.5">
            <li v-for="item in g.items" :key="item.key">
              <RouterLink
                :to="item.path"
                class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm lg:min-h-10"
                :class="
                  isActivePath(item.path, route.path)
                    ? 'bg-side-pill font-semibold text-on-side-pill'
                    : 'text-side-dim hover:bg-side-hover hover:text-on-side'
                "
                :aria-current="isActivePath(item.path, route.path) ? 'page' : undefined"
                active-class=""
                exact-active-class=""
              >
                <component :is="NAV_ICONS[item.icon]" :size="16" aria-hidden="true" />
                {{ item.label }}
              </RouterLink>
            </li>
          </ul>
        </section>
      </template>
    </nav>
  </div>
</template>
