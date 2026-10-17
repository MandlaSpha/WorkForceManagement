<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import BrandMark from '@/shared/ui/BrandMark.vue'

import { isActivePath } from '../model/active'
import { NAV_ICONS } from '../model/icons'
import { visibleNav } from '../model/visible-nav'

const session = useSessionStore()
const route = useRoute()
const groups = computed(() => (session.user ? visibleNav(session.user) : []))
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="px-4 pb-3 pt-5">
      <BrandMark />
      <p class="mt-2 text-sm font-semibold text-ink">Workforce Management</p>
      <p class="text-[10px] font-medium uppercase tracking-wider text-ink-muted">
        Technology people
      </p>
    </div>

    <nav aria-label="Main navigation" class="flex-1 overflow-y-auto px-2 pb-4">
      <section v-for="g in groups" :key="g.group" class="mt-4">
        <h2 class="px-2 text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
          {{ g.group }}
        </h2>
        <ul class="mt-1 space-y-0.5">
          <li v-for="item in g.items" :key="item.key">
            <RouterLink
              :to="item.path"
              class="flex min-h-11 items-center gap-3 lg:min-h-9 rounded-lg px-2 text-sm"
              :class="
                isActivePath(item.path, route.path)
                  ? 'bg-brand-soft font-medium text-brand-ink'
                  : 'text-ink-muted hover:bg-surface-muted hover:text-ink'
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
    </nav>

    <p class="border-t border-line px-4 py-3 text-[11px] text-ink-muted">
      The interval engine is the spine. Coverage · Requirement · Variance @ 30-min
    </p>
  </div>
</template>
