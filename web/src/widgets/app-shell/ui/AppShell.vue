<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import SidebarNav from './SidebarNav.vue'
import TopBar from './TopBar.vue'

const route = useRoute()
const menuOpen = ref(false)

// Close the mobile drawer after navigating.
watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
  },
)

// Escape closes the drawer, as it does any dialog-like panel.
function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && menuOpen.value) menuOpen.value = false
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="flex h-dvh overflow-hidden bg-canvas text-ink">
    <a
      href="#main"
      class="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
    >
      Skip to main content
    </a>

    <!-- Backdrop for the mobile drawer -->
    <div
      v-if="menuOpen"
      class="fixed inset-0 z-30 bg-black/40 lg:hidden"
      aria-hidden="true"
      @click="menuOpen = false"
    />

    <aside
      id="sidebar"
      class="fixed inset-y-0 left-0 z-40 w-72 shrink-0 bg-side text-on-side shadow-[var(--shadow-pop)] transition-transform lg:static lg:m-3 lg:w-64 lg:translate-x-0 lg:rounded-[1.5rem]"
      :class="menuOpen ? 'translate-x-0' : 'invisible -translate-x-full lg:visible'"
    >
      <SidebarNav />
    </aside>

    <div class="flex min-w-0 flex-1 flex-col">
      <TopBar :menu-open="menuOpen" @toggle-menu="menuOpen = !menuOpen" />
      <main id="main" class="flex-1 overflow-y-auto px-4 pb-8 pt-2 sm:px-6" tabindex="-1">
        <div :key="route.path" class="page-enter"><RouterView /></div>
      </main>
    </div>
  </div>
</template>
