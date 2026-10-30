<script setup lang="ts">
import { computed, ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { coverage, measured, promise, useContracts, useCustomers } from '@/entities/contract'
import type { ContractRow } from '@/entities/contract'
import { useSessionStore } from '@/entities/session'
import { AssigneesForm } from '@/features/commercial/assignees'
import { ContractForm } from '@/features/commercial/contract'
import { CustomerForm } from '@/features/commercial/customer'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'contracts')
const session = useSessionStore()
// Cosmetic: the API refuses changes from any other role.
const canChange = computed(() => session.user?.role === 'admin')

const contracts = useContracts()
const customers = useCustomers()
const queues = useQueues()

// "new" shows the add form; a contract shows the change form for it.
const editing = ref<ContractRow | 'new' | null>(null)
const list = computed(() => contracts.data.value ?? [])
const atRisk = computed(() => list.value.filter((c) => c.atRisk).length)
const totalCalls = computed(() => list.value.reduce((sum, c) => sum + c.offered, 0))
const totalShort = computed(() => list.value.reduce((sum, c) => sum + c.underIntervals, 0))
const bar = (pct: number | null): string => `${Math.min(100, Math.max(0, pct ?? 0))}%`
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Contracts'" :subtitle="screen?.subtitle">
    <template v-if="canChange" #actions>
      <AppButton v-if="editing === null" @click="editing = 'new'">Add contract</AppButton>
    </template>
  </PageHeader>

  <section class="space-y-6" aria-live="polite">
    <div v-if="canChange" class="space-y-4">
      <CustomerForm />
      <ContractForm
        v-if="editing !== null"
        :key="editing === 'new' ? 'new' : editing.id"
        :contract="editing === 'new' ? null : editing"
        :customers="customers.data.value ?? []"
        :queues="queues.data.value ?? []"
        @saved="editing = null"
        @cancel="editing = null"
      />
    </div>

    <details v-if="canChange && (customers.data.value ?? []).length > 0" class="space-y-3">
      <summary class="cursor-pointer text-sm font-medium text-brand-ink">
        Who looks after each customer
      </summary>
      <div class="mt-3 grid gap-3 md:grid-cols-2">
        <AssigneesForm v-for="c in customers.data.value" :key="c.id" :customer="c" />
      </div>
    </details>

    <p v-if="contracts.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="contracts.isError.value" tone="danger">
      Could not load the contracts. {{ problemMessage(contracts.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(contracts.data.value ?? []).length === 0" data-testid="no-contracts">
      There are no contracts yet.
      <template v-if="canChange"
        >Add a customer, then a contract that holds its queues to a promise.</template
      >
    </NoticeBox>
    <template v-else>
      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Contracts at a glance">
        <StatTile label="Contracts" :value="list.length" tint="brand" />
        <StatTile
          label="At risk"
          :value="atRisk"
          :tint="atRisk > 0 ? 'danger' : 'ok'"
          data-testid="risk-summary"
        >
          of {{ list.length }} {{ list.length === 1 ? 'contract is' : 'contracts are' }} at risk
        </StatTile>
        <StatTile label="Calls, last 28 days" :value="totalCalls" tint="ok" />
        <StatTile label="Short this week" :value="totalShort" tint="warn">half-hours</StatTile>
      </ul>

      <ul class="grid gap-4 lg:grid-cols-2" aria-label="Contracts" data-testid="contracts-list">
        <li
          v-for="c in list"
          :key="c.id"
          class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
          :data-testid="`contract-${c.id}`"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-xs text-ink-muted">{{ c.customer }}</p>
              <h2 class="truncate text-base font-semibold text-ink">
                {{ c.name }}<template v-if="!c.active"> · ended</template>
              </h2>
            </div>
            <span
              class="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold"
              :class="c.atRisk ? 'bg-danger-soft text-danger' : 'bg-ok-soft text-ok'"
            >
              {{ c.atRisk ? 'At risk' : 'OK' }}
            </span>
          </div>

          <ul class="mt-2 flex flex-wrap gap-1.5" aria-label="Queues">
            <li
              v-for="q in c.queues"
              :key="q.id"
              class="rounded-full bg-surface-muted px-2.5 py-0.5 text-xs text-ink"
            >
              {{ q.name }}
            </li>
            <li v-if="c.queues.length === 0" class="text-xs text-ink-muted">No queues</li>
          </ul>

          <div class="mt-4">
            <div class="flex items-baseline justify-between gap-3 text-sm">
              <span class="tabular-nums text-ink">{{ measured(c) }}</span>
              <span class="tabular-nums text-ink-muted">Promised {{ promise(c) }}</span>
            </div>
            <div
              class="relative mt-2 h-2 rounded-full bg-surface-muted"
              role="img"
              :aria-label="`Measured against ${c.slTargetPct}% promised`"
            >
              <div
                class="h-full rounded-full"
                :class="c.atRisk ? 'bg-danger' : 'bg-brand'"
                :style="{ width: bar(c.measuredSlPct) }"
              ></div>
              <div
                class="absolute -top-1 h-4 w-0.5 rounded bg-ink"
                :style="{ left: bar(c.slTargetPct) }"
                aria-hidden="true"
              ></div>
            </div>
          </div>

          <p class="mt-3 text-sm text-ink">
            <span class="text-ink-muted">This week:</span> {{ coverage(c) }}
          </p>
          <ul
            v-if="c.risks.length > 0"
            class="mt-2 list-disc space-y-0.5 pl-4 text-xs text-ink-muted"
          >
            <li v-for="r in c.risks" :key="r">{{ r }}</li>
          </ul>

          <button
            v-if="canChange"
            type="button"
            class="mt-3 text-sm font-medium text-brand-ink underline"
            :aria-label="`Change ${c.customer} ${c.name}`"
            @click="editing = c"
          >
            Change
          </button>
        </li>
      </ul>
    </template>
  </section>
</template>
