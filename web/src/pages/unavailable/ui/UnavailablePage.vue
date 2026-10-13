<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { homePathFor, useSessionStore } from '@/entities/session'
import PageHeader from '@/shared/ui/PageHeader.vue'

const session = useSessionStore()
</script>

<template>
  <PageHeader
    title="This is not part of your plan"
    subtitle="This feature is not switched on for your organisation. If you need it, ask your administrator to contact VMK."
  />
  <RouterLink
    :to="session.user ? homePathFor(session.user.role) : '/'"
    class="text-sm font-medium text-brand-ink underline"
  >
    Go to your home page
  </RouterLink>
</template>
