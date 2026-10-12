<script setup lang="ts">
import { ROLE_LABELS, useSessionStore } from '@/entities/session'
import { useContextStore } from '@/features/context-filters'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const session = useSessionStore()
const context = useContextStore()
const dashboard = NAV_ITEMS.find((item) => item.key === 'dashboard')
</script>

<template>
  <PageHeader
    eyebrow="Overview"
    title="Dashboard"
    :subtitle="`${dashboard?.subtitle ?? ''} Week of ${context.weekLabel}.`"
  />

  <section class="space-y-4">
    <p class="text-sm text-ink">
      Signed in as <strong>{{ session.user?.displayName }}</strong> ({{
        session.user ? ROLE_LABELS[session.user.role] : ''
      }}).
    </p>
    <NoticeBox>
      No call data has been imported yet, so there is nothing to measure. Coverage, service level
      and the other tiles appear here once a call detail report is imported (Phase 1). Until then
      this page shows no figures rather than invented ones.
    </NoticeBox>
  </section>
</template>
