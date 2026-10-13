<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useSessionStore } from '@/entities/session'

const session = useSessionStore()
const queryClient = useQueryClient()
const route = useRoute()
const router = useRouter()

// Cached answers belong to the person who asked for them. When the signed-in person (or their
// role) changes, including sign-out and an expired session, drop everything, so the next person
// on a shared browser can never see the previous person's figures.
watch(
  () => (session.user ? `${session.user.username}:${session.user.role}` : null),
  () => queryClient.clear(),
)

// When the server ends the session (idle timeout) the person must not be left looking at a
// protected screen. The route guard only runs on navigation, so move them to sign-in here and
// remember where they were.
watch(
  () => session.status,
  (status) => {
    if (status === 'anonymous' && !route.meta.public) {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    }
  },
)
</script>

<template>
  <RouterView />
</template>
