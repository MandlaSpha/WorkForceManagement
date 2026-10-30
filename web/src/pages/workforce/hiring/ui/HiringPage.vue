<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useHiringPlan, useHiringPlans } from '@/entities/workforce/hiring-plan'
import { useSessionStore } from '@/entities/session'
import { DeletePlanButton, HiringPlanForm } from '@/features/hiring/plan'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import BarSeries, { type BarItem } from '@/shared/ui/BarSeries.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'hiring')
const session = useSessionStore()
// Cosmetic: the API refuses everything else.
const canChange = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const plans = useHiringPlans()
const picked = ref('')
const id = computed(() => (picked.value === '' ? null : Number(picked.value)))
const plan = useHiringPlan(id)
const mode = ref<'view' | 'edit' | 'new'>('view')

watch(
  () => plans.data.value,
  (list) => {
    if (list && picked.value === '' && list.length > 0) picked.value = String(list[0]!.id)
  },
  { immediate: true },
)
function saved(newId: number): void {
  picked.value = String(newId)
  mode.value = 'view'
}

const options = computed(() =>
  (plans.data.value ?? []).map((p) => ({ value: String(p.id), label: p.name })),
)
const monthLabel = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-ZA', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  })
// Hires month by month: the plan's output. A red bar is a month the plan still falls short; the
// hover says what was needed and what is at full strength.
const MONTH_SHORT = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-ZA', { month: 'short', timeZone: 'UTC' })
const chartItems = computed<BarItem[]>(() =>
  (plan.data.value?.rows ?? []).map((r) => ({
    label: MONTH_SHORT(r.month),
    title: `${monthLabel(r.month)}: hire ${r.hires}; ${one(r.required)} needed, ${one(r.effective)} at full strength`,
    value: r.hires,
    tone: r.gap < -0.05 ? ('high' as const) : undefined,
    mark: r.hires > 0 ? String(r.hires) : undefined,
  })),
)
const one = (n: number) => n.toLocaleString('en-ZA', { maximumFractionDigits: 1 })
const rands = (n: number) =>
  `R ${n.toLocaleString('en-ZA', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
</script>

<template>
  <PageHeader
    eyebrow="Operate"
    :title="screen?.label ?? 'Hiring plan'"
    :subtitle="screen?.subtitle"
  >
    <template v-if="canChange" #actions>
      <button
        type="button"
        class="inline-flex min-h-10 items-center rounded-lg border border-line bg-surface px-4 text-sm font-medium text-ink hover:bg-surface-muted"
        @click="mode = mode === 'new' ? 'view' : 'new'"
      >
        {{ mode === 'new' ? 'Cancel' : 'New plan' }}
      </button>
    </template>
  </PageHeader>

  <section class="space-y-4" aria-live="polite">
    <HiringPlanForm
      v-if="mode === 'new' && canChange"
      :plan="null"
      :sees-pay="canChange"
      @saved="saved"
    />

    <p v-if="plans.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="plans.isError.value" tone="danger">
      Could not load the plans. {{ problemMessage(plans.error.value) }}
    </NoticeBox>
    <NoticeBox
      v-else-if="(plans.data.value ?? []).length === 0 && mode !== 'new'"
      data-testid="no-plans"
    >
      There is no hiring plan yet.
    </NoticeBox>

    <template v-else-if="(plans.data.value ?? []).length > 0">
      <div class="flex flex-wrap items-end gap-4">
        <div class="w-64">
          <SelectField v-model="picked" label="Plan" :options="options" />
        </div>
        <template v-if="canChange && plan.data.value">
          <button
            type="button"
            class="text-sm font-medium text-brand-ink underline"
            @click="mode = mode === 'edit' ? 'view' : 'edit'"
          >
            {{ mode === 'edit' ? 'Stop editing' : 'Edit these inputs' }}
          </button>
          <DeletePlanButton :plan-id="plan.data.value.id" :name="plan.data.value.name" />
        </template>
      </div>

      <HiringPlanForm
        v-if="mode === 'edit' && canChange && plan.data.value"
        :key="plan.data.value.id"
        :plan="plan.data.value"
        :sees-pay="canChange"
        @saved="saved"
      />

      <p v-if="plan.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="plan.isError.value" tone="danger">
        Could not load the plan. {{ problemMessage(plan.error.value) }}
      </NoticeBox>

      <template v-else-if="plan.data.value">
        <ul
          class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          aria-label="Summary"
          data-testid="summary"
        >
          <StatTile
            label="People to hire"
            :value="plan.data.value.totalHires"
            tint="brand"
            data-testid="total-hires"
          />
          <StatTile
            label="Months short"
            :value="plan.data.value.shortfallMonths"
            tint="danger"
            data-testid="short-months"
          >
            {{ plan.data.value.unavoidableMonths }} too soon for any hire to help
          </StatTile>
          <StatTile
            v-if="plan.data.value.totalCostRands !== null"
            label="Cost over the plan"
            :value="plan.data.value.totalCostRands"
            :format="rands"
            tint="warn"
            data-testid="total-cost"
          />
        </ul>

        <section
          class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
          aria-labelledby="hiring-chart"
        >
          <h2 id="hiring-chart" class="text-base font-semibold text-ink">Hires each month</h2>
          <div class="mt-6">
            <BarSeries
              :items="chartItems"
              value-label="People to hire"
              summary="People to hire each month. A red bar is a month the plan still falls short."
            />
          </div>
        </section>

        <details class="rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" open>
          <summary class="cursor-pointer px-4 py-3 text-base font-semibold text-ink">
            Month by month
          </summary>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[40rem] text-left text-sm" data-testid="plan-table">
              <caption class="sr-only">
                Month by month
              </caption>
              <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
                <tr>
                  <th scope="col" class="px-4 py-2 font-medium">Month</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Needed</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Employed</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Hire</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">At full strength</th>
                  <th scope="col" class="px-3 py-2 text-right font-medium">Short or spare</th>
                  <th
                    v-if="plan.data.value.totalCostRands !== null"
                    scope="col"
                    class="px-3 py-2 text-right font-medium"
                  >
                    Cost
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="r in plan.data.value.rows"
                  :key="r.month"
                  class="border-b border-line"
                  :data-testid="`month-${r.month}`"
                >
                  <th scope="row" class="px-4 py-2 text-left font-medium">
                    {{ monthLabel(r.month) }}
                  </th>
                  <td class="px-3 py-2 text-right tabular-nums">{{ one(r.required) }}</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ one(r.headcount) }}</td>
                  <td class="px-3 py-2 text-right font-semibold tabular-nums">
                    {{ r.hires || '-' }}
                  </td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ one(r.effective) }}</td>
                  <td
                    class="px-3 py-2 text-right tabular-nums"
                    :class="r.gap < -0.05 ? 'text-danger' : 'text-ink'"
                    data-testid="gap"
                  >
                    {{ r.gap > 0.05 ? '+' : '' }}{{ one(r.gap) }}
                    <span v-if="r.unavoidable" class="block text-[11px] text-ink-muted"
                      >too soon to hire for</span
                    >
                  </td>
                  <td v-if="r.costRands !== null" class="px-3 py-2 text-right tabular-nums">
                    {{ rands(r.costRands) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </template>
    </template>
  </section>
</template>
