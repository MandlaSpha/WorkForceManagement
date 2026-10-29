<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { useSessionStore } from '@/entities/session'

import { crumbsFor } from '../model/breadcrumb'
import { visibleNav } from '../model/visible-nav'

const session = useSessionStore()
const route = useRoute()
const crumbs = computed(() =>
  session.user ? crumbsFor(visibleNav(session.user), String(route.name ?? '')) : null,
)
</script>

<template>
  <nav v-if="crumbs" aria-label="Breadcrumb" class="hidden self-center md:block">
    <ol class="flex items-center gap-1.5 text-sm text-ink-muted">
      <li>
        <RouterLink :to="crumbs.groupPath" class="hover:text-ink hover:underline">{{
          crumbs.group
        }}</RouterLink>
      </li>
      <li aria-hidden="true"><ChevronRight :size="14" /></li>
      <li class="font-medium text-ink" aria-current="page">{{ crumbs.title }}</li>
    </ol>
  </nav>
</template>
