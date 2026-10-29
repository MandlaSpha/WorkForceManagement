<script setup lang="ts">
import { ChevronRight, Settings } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { canOpen, useSessionStore } from '@/entities/session'

import { isActivePath } from '../model/active'
import { NAV_ICONS } from '../model/icons'
import { settingsItems } from '../model/visible-nav'
import AccountMenu from './AccountMenu.vue'
import CoverageCard from './CoverageCard.vue'

const session = useSessionStore()
const route = useRoute()

const items = computed(() => (session.user ? settingsItems(session.user) : []))
const showCoverage = computed(() => (session.user ? canOpen(session.user, 'planner') : false))

// Open by choice, and open whenever you are standing on one of its screens.
const chosen = ref(false)
const open = computed(
  () => chosen.value || items.value.some((i) => isActivePath(i.path, route.path)),
)
</script>

<template>
  <div class="space-y-2 border-t border-side-line px-3 pb-3 pt-3" data-testid="sidebar-footer">
    <div v-if="items.length > 0">
      <button
        type="button"
        class="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-sm text-side-dim hover:bg-side-hover hover:text-on-side lg:min-h-10"
        :aria-expanded="open"
        aria-controls="nav-settings"
        @click="chosen = !open"
      >
        <Settings :size="16" aria-hidden="true" />
        <span class="flex-1 text-left">Settings</span>
        <ChevronRight
          :size="14"
          class="transition-transform"
          :class="open ? 'rotate-90' : ''"
          aria-hidden="true"
        />
      </button>
      <div class="settings-panel" :class="open ? 'is-open' : ''">
        <ul id="nav-settings" class="min-h-0 space-y-0.5 overflow-hidden" :inert="!open">
          <li v-for="item in items" :key="item.key">
            <RouterLink
              :to="item.path"
              class="flex min-h-11 items-center gap-3 rounded-xl pl-9 pr-3 text-sm lg:min-h-10"
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
      </div>
    </div>

    <CoverageCard v-if="showCoverage" />
    <AccountMenu />
  </div>
</template>

<style scoped>
.settings-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 220ms ease-out;
}
.settings-panel.is-open {
  grid-template-rows: 1fr;
}
@media (prefers-reduced-motion: reduce) {
  .settings-panel {
    transition: none;
  }
}
</style>
