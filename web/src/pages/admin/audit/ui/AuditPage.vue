<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  auditCsvUrl,
  NO_FILTERS,
  PAGE_SIZE,
  useAuditEvents,
  type AuditFilters,
} from '@/entities/audit-log'
import { ChainStatus } from '@/features/audit/chain-status'
import { FilterBar } from '@/features/audit/filter-log'
import { LogTable } from '@/features/audit/log-table'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'audit')
const applied = ref<AuditFilters>({ ...NO_FILTERS })
const page = ref(1)
const events = useAuditEvents(applied, page)

const total = computed(() => events.data.value?.total ?? 0)
const lastPage = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const csvUrl = computed(() => auditCsvUrl(applied.value))

function apply(filters: AuditFilters): void {
  applied.value = filters
  page.value = 1
}
</script>

<template>
  <PageHeader eyebrow="Admin" :title="screen?.label ?? 'Audit log'" :subtitle="screen?.subtitle" />

  <div class="space-y-6" aria-live="polite">
    <ChainStatus />

    <FilterBar :applied="applied" @apply="apply" />

    <p v-if="events.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="events.isError.value" tone="danger">
      Could not load the audit log. {{ problemMessage(events.error.value) }}
    </NoticeBox>
    <template v-else-if="events.data.value">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-sm text-ink-muted" data-testid="audit-count">
          {{ total }} event{{ total === 1 ? '' : 's' }}, newest first
        </p>
        <a
          :href="csvUrl"
          class="text-sm font-medium text-brand-ink underline"
          download
          data-testid="audit-csv"
        >
          Download these as CSV (the download is recorded)
        </a>
      </div>

      <NoticeBox v-if="events.data.value.items.length === 0">
        No events match these filters.
      </NoticeBox>
      <LogTable v-else :events="events.data.value.items" />

      <nav class="flex items-center gap-3" aria-label="Pages">
        <AppButton variant="secondary" :disabled="page <= 1" @click="page -= 1">Newer</AppButton>
        <span class="text-sm text-ink-muted" data-testid="audit-page">
          Page {{ page }} of {{ lastPage }}
        </span>
        <AppButton variant="secondary" :disabled="page >= lastPage" @click="page += 1">
          Older
        </AppButton>
      </nav>
    </template>
  </div>
</template>
