<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import { gapLabel, hours, pct, useCosts, useUtilisation } from '@/entities/workforce/utilisation'
import { TermsForm } from '@/features/utilisation/set-terms'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

import CostPanel from './CostPanel.vue'
import GroupTable from './GroupTable.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'utilisation')
const session = useSessionStore()

const thisMonth = new Date()
  .toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
  .slice(0, 7)
const month = ref(thisMonth)
const first = computed(() => `${month.value}-01`)
const report = useUtilisation(first)

// Cosmetic: the API refuses pay figures to everyone but planners and admins.
const role = computed(() => session.user?.role ?? '')
const seesCost = computed(() => ['planner', 'admin'].includes(role.value))
const canSetTerms = computed(() => role.value === 'admin')
const costs = useCosts(first, seesCost)

const termsFor = ref<number | null>(null)
const termsContract = computed(() =>
  report.data.value?.contracts.find((c) => c.contractId === termsFor.value),
)
</script>

<template>
  <PageHeader
    eyebrow="Insight"
    :title="screen?.label ?? 'Utilisation'"
    :subtitle="screen?.subtitle"
  />

  <section class="space-y-4" aria-live="polite">
    <label class="flex items-center gap-2 text-sm text-ink">
      Month
      <input
        v-model="month"
        type="month"
        class="rounded-lg border border-line bg-surface px-2 py-1"
      />
    </label>

    <p v-if="report.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="report.isError.value" tone="danger" data-testid="utilisation-error">
      Could not load utilisation. {{ problemMessage(report.error.value) }}
    </NoticeBox>

    <template v-else-if="report.data.value">
      <NoticeBox data-testid="modelled-note">
        Modelled from the published roster, not from timesheets. Worked time is the paid time of the
        shifts; billable time is the part on a contracted queue, less training, meetings, coaching
        and other time inside the shift. Where a contract has no target set, 75% is assumed and
        marked.
      </NoticeBox>

      <NoticeBox v-if="report.data.value.teams.length === 0" data-testid="utilisation-none">
        Nobody is on a published roster in that month (or none in your view).
      </NoticeBox>

      <template v-else>
        <h2 class="text-base font-semibold text-ink">Teams</h2>
        <GroupTable caption="Utilisation by team" kind="team" :rows="report.data.value.teams" />

        <h2 class="text-base font-semibold text-ink">Customers</h2>
        <GroupTable
          caption="Utilisation by customer"
          kind="customer"
          :rows="report.data.value.customers"
        />

        <h2 class="text-base font-semibold text-ink">Contracts</h2>
        <GroupTable
          caption="Utilisation by contract"
          kind="contract"
          :rows="report.data.value.contracts"
        />

        <section v-if="canSetTerms && report.data.value.contracts.length" class="space-y-2">
          <label class="flex items-center gap-2 text-sm text-ink">
            Set the terms of
            <select
              v-model="termsFor"
              class="rounded-lg border border-line bg-surface px-2 py-1"
              aria-label="Contract to set terms for"
            >
              <option :value="null">Choose a contract</option>
              <option
                v-for="c in report.data.value.contracts"
                :key="c.contractId ?? 0"
                :value="c.contractId"
              >
                {{ c.name }} ({{ c.customer }})
              </option>
            </select>
          </label>
          <TermsForm
            v-if="termsContract && termsContract.contractId != null"
            :key="termsContract.contractId"
            :contract-id="termsContract.contractId"
            :contract-name="termsContract.name"
            :target-pct="termsContract.targetPct ?? null"
          />
        </section>

        <section
          v-if="report.data.value.people.length"
          class="space-y-2"
          aria-labelledby="people-heading"
        >
          <h2 id="people-heading" class="text-base font-semibold text-ink">People</h2>
          <p class="text-xs text-ink-muted">
            In employee-number order. This is not a ranking and is not shown to colleagues.
          </p>
          <div class="overflow-x-auto rounded-xl border border-line bg-surface">
            <table class="w-full text-left text-sm">
              <caption class="sr-only">
                Utilisation of each person
              </caption>
              <thead class="text-xs text-ink-muted">
                <tr>
                  <th scope="col" class="px-3 py-2">Person</th>
                  <th scope="col" class="px-3 py-2">Worked (h)</th>
                  <th scope="col" class="px-3 py-2">Billable (h)</th>
                  <th scope="col" class="px-3 py-2">Utilisation</th>
                  <th scope="col" class="px-3 py-2">Gap</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="p in report.data.value.people"
                  :key="p.employeeId"
                  class="border-t border-line"
                  :data-testid="`person-${p.empNo}`"
                >
                  <th scope="row" class="px-3 py-2 font-medium text-ink">
                    {{ p.employee }} <span class="text-ink-muted">({{ p.empNo }})</span>
                  </th>
                  <td class="px-3 py-2">{{ hours(p.workedMin) }}</td>
                  <td class="px-3 py-2">{{ hours(p.billableMin) }}</td>
                  <td class="px-3 py-2 font-semibold">{{ pct(p.utilisationPct) }}</td>
                  <td class="px-3 py-2">{{ gapLabel(p.gapPct) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </template>

    <template v-if="seesCost">
      <p v-if="costs.isPending.value" class="text-sm text-ink-muted">Loading cost…</p>
      <NoticeBox v-else-if="costs.isError.value" tone="danger" data-testid="cost-error">
        Could not load cost. {{ problemMessage(costs.error.value) }}
      </NoticeBox>
      <CostPanel v-else-if="costs.data.value" :costs="costs.data.value" />
    </template>
  </section>
</template>
