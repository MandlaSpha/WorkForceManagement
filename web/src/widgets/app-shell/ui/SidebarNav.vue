<script setup lang="ts">
import { ChevronRight, Search } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import type { NavGroup } from '@/shared/config'
import BrandMark from '@/shared/ui/BrandMark.vue'
import ExpandTransition from '@/shared/ui/ExpandTransition.vue'

import { isActivePath } from '../model/active'
import { NAV_ICONS } from '../model/icons'
import {
  activeGroup,
  afterClick,
  NAV_OPEN_KEY,
  openGroups,
  parseRemembered,
} from '../model/nav-state'
import { badgeText, useNavCounts } from '../model/nav-counts'
import { paletteOpen } from '../model/palette'
import { mainNav } from '../model/visible-nav'
import SidebarFooter from './SidebarFooter.vue'

const session = useSessionStore()
const route = useRoute()
// Admin screens live under Settings at the foot; the search palette still reaches them.
const groups = computed(() => (session.user ? mainNav(session.user) : []))

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

// Going to a screen in a group that is closed (a link in a page, the search palette, back/forward) opens
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

// What is waiting for this person, per screen; a group shows the sum while it is closed.
const counts = useNavCounts()
const groupCount = (g: { items: { key: string }[] }): number =>
  g.items.reduce((sum, i) => sum + (counts.value[i.key] ?? 0), 0)
</script>

<template>
  <div class="sidebar-stagger flex h-full flex-col">
    <div class="px-5 pb-3 pt-5">
      <BrandMark />
      <p class="mt-2.5 text-sm font-semibold text-on-side">Workforce Management</p>
    </div>

    <div class="px-4 pb-2">
      <button
        type="button"
        class="flex h-10 w-full items-center gap-2 rounded-xl border border-side-line bg-side-hover px-3 text-sm text-side-faint hover:text-on-side"
        aria-haspopup="dialog"
        aria-keyshortcuts="Control+K Meta+K /"
        @click="paletteOpen = true"
      >
        <Search :size="14" aria-hidden="true" />
        <span class="flex-1 text-left">Search</span>
        <kbd
          class="hidden rounded-md border border-side-line px-1.5 text-[10px] lg:block"
          aria-hidden="true"
          >Ctrl K</kbd
        >
      </button>
    </div>

    <nav aria-label="Main navigation" class="flex min-h-0 flex-1 flex-col">
      <div class="quiet-scroll flex-1 overflow-y-auto px-3 pb-4">
        <div>
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
                  class="transition-transform duration-300"
                  :class="open.has(g.group) ? 'rotate-90' : ''"
                  aria-hidden="true"
                />
                <span class="flex-1 text-left">{{ g.group }}</span>
                <span
                  v-if="!open.has(g.group) && groupCount(g) > 0"
                  class="inline-flex min-w-4 items-center justify-center rounded-full bg-[#f2c15c] px-1 text-[10px] font-semibold leading-4 text-[#1b1405]"
                  :aria-label="`${groupCount(g)} waiting`"
                  >{{ badgeText(groupCount(g)) }}</span
                >
                <span class="font-normal normal-case tracking-normal">{{ g.items.length }}</span>
              </button>
            </h2>
            <ExpandTransition>
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
                    <span class="flex-1">{{ item.label }}</span>
                    <span
                      v-if="(counts[item.key] ?? 0) > 0"
                      class="inline-flex min-w-5 items-center justify-center rounded-full bg-[#f2c15c] px-1.5 text-[11px] font-semibold leading-5 text-[#1b1405]"
                      data-testid="nav-badge"
                    >
                      <span aria-hidden="true">{{ badgeText(counts[item.key] ?? 0) }}</span>
                      <span class="sr-only">{{ counts[item.key] }} waiting</span>
                    </span>
                  </RouterLink>
                </li>
              </ul>
            </ExpandTransition>
          </section>
        </div>
      </div>

      <!-- Pinned below the scrolling list: Settings, this week's coverage, and the user card. -->
      <SidebarFooter />
    </nav>
  </div>
</template>
