<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { homePathFor, useSessionStore } from '@/entities/session'
import PageHeader from '@/shared/ui/PageHeader.vue'

const session = useSessionStore()
</script>

<template>
  <PageHeader title="Page not found" subtitle="That address doesn't match any screen." />
  <RouterLink
    :to="session.user ? homePathFor(session.user.role) : '/'"
    class="text-sm font-medium text-brand-ink underline"
  >
    Go to your home page
  </RouterLink>
</template>
