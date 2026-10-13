<script setup lang="ts">
import { computed } from 'vue'

import { safeRedirect } from '@/shared/lib/redirect'

import type { SignInProvider } from '../model/providers'

const props = defineProps<{
  providers: readonly SignInProvider[]
  /** Where to go once signed in. Only same-site paths are passed on to the server. */
  next?: string
}>()

const links = computed(() =>
  props.providers
    .filter((p) => p.flow === 'redirect' && p.startUrl)
    .map((p) => ({
      id: p.id,
      label: p.label,
      href: `${p.startUrl}?next=${encodeURIComponent(safeRedirect(props.next, '/'))}`,
    })),
)
</script>

<template>
  <ul v-if="links.length" class="space-y-2" aria-label="Single sign-on">
    <li v-for="link in links" :key="link.id">
      <!-- A normal link, not a fetch: the browser must navigate to the identity provider. -->
      <a
        :href="link.href"
        class="inline-flex min-h-10 w-full items-center justify-center rounded-lg border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
      >
        Sign in with {{ link.label }}
      </a>
    </li>
  </ul>
</template>
