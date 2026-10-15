<script setup lang="ts">
import { computed, ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { coverage, measured, promise, useContracts, useCustomers } from '@/entities/contract'
import type { ContractRow } from '@/entities/contract'
import { useSessionStore } from '@/entities/session'
import { ContractForm } from '@/features/commercial/contract'
import { CustomerForm } from '@/features/commercial/customer'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'contracts')
const session = useSessionStore()
// Cosmetic: the API refuses changes from any other role.
const canChange = computed(() => session.user?.role === 'admin')

const contracts = useContracts()
const customers = useCustomers()
const queues = useQueues()

// "new" shows the add form; a contract shows the change form for it.
const editing = ref<ContractRow | 'new' | null>(null)
const atRisk = computed(() => (contracts.data.value ?? []).filter((c) => c.atRisk).length)
</script>

<template>
  <PageHeader eyebrow="Operate" :title="screen?.label ?? 'Contracts'" :subtitle="screen?.subtitle">
    <template v-if="canChange" #actions>
      <AppButton v-if="editing === null" @click="editing = 'new'">Add contract</AppButton>
    </template>
  </PageHeader>

  <section class="space-y-6" aria-live="polite">
    <NoticeBox data-testid="how-measured">
      <strong>Measured</strong> is the service level actually achieved over the last 28 days of
      imported calls. <strong>This week</strong> is <em>modelled</em>: the roster against the
      published forecast. Neither is invented: with no calls or no forecast the figure is missing,
      not zero.
    </NoticeBox>

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
      <p class="text-sm text-ink" data-testid="risk-summary">
        <strong>{{ atRisk }}</strong> of {{ contracts.data.value?.length }}
        {{ contracts.data.value?.length === 1 ? 'contract is' : 'contracts are' }} at risk.
      </p>
      <div class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full min-w-[52rem] text-left text-sm" data-testid="contracts-table">
          <caption class="sr-only">
            Contracts
          </caption>
          <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-4 py-2 font-medium">Contract</th>
              <th scope="col" class="px-3 py-2 font-medium">Queues</th>
              <th scope="col" class="px-3 py-2 font-medium">Promised</th>
              <th scope="col" class="px-3 py-2 font-medium">Measured</th>
              <th scope="col" class="px-3 py-2 font-medium">This week</th>
              <th scope="col" class="px-3 py-2 font-medium">Status</th>
              <th v-if="canChange" scope="col" class="px-4 py-2 text-right font-medium">
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in contracts.data.value"
              :key="c.id"
              class="border-b border-line align-top"
              :data-testid="`contract-${c.id}`"
            >
              <th scope="row" class="px-4 py-2 text-left font-medium text-ink">
                {{ c.customer }}
                <span class="block text-xs font-normal text-ink-muted">
                  {{ c.name }}<template v-if="!c.active"> · ended</template>
                </span>
              </th>
              <td class="px-3 py-2">{{ c.queues.map((q) => q.name).join(', ') || '—' }}</td>
              <td class="px-3 py-2 tabular-nums">{{ promise(c) }}</td>
              <td class="px-3 py-2">{{ measured(c) }}</td>
              <td class="px-3 py-2">{{ coverage(c) }}</td>
              <td class="px-3 py-2">
                <span
                  v-if="c.atRisk"
                  class="rounded-full bg-danger-soft px-2 py-0.5 text-[11px] font-semibold text-danger"
                >
                  At risk
                </span>
                <span v-else class="text-ink-muted">OK</span>
                <ul v-if="c.risks.length > 0" class="mt-1 list-disc pl-4 text-xs text-ink-muted">
                  <li v-for="r in c.risks" :key="r">{{ r }}</li>
                </ul>
              </td>
              <td v-if="canChange" class="px-4 py-2 text-right">
                <button
                  type="button"
                  class="text-sm font-medium text-brand-ink underline"
                  :aria-label="`Change ${c.customer} ${c.name}`"
                  @click="editing = c"
                >
                  Change
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
