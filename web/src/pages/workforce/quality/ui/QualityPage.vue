<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import {
  KIND_LABEL,
  scoreText,
  useMyQuality,
  useQualityPerson,
  useQualityTeam,
} from '@/entities/workforce/quality'
import { QualityImportPanel } from '@/features/quality/import-results'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import SelectField from '@/shared/ui/SelectField.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'quality')

// Cosmetic: the API decides who may load a file, who may review a team, and who has own results.
const role = computed(() => session.user?.role ?? '')
const canImport = computed(() => ['planner', 'admin'].includes(role.value))
const canReview = computed(() => ['lead', 'planner', 'admin'].includes(role.value))

const days = ref('90')
const WINDOWS = [
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 180 days' },
  { value: '365', label: 'Last 12 months' },
]
const windowDays = computed(() => Number(days.value))

const team = useQualityTeam(windowDays, canReview)
const mine = useMyQuality(windowDays, true)
const chosen = ref<number | null>(null)
const person = useQualityPerson(chosen, windowDays)

function coaching(p: { coachingDue?: string | null; coachingIsDue: boolean }): string {
  if (!p.coachingDue) return 'None set'
  return p.coachingIsDue ? `Due (${p.coachingDue})` : p.coachingDue
}
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Quality'" :subtitle="screen?.subtitle">
    <template #actions>
      <div class="w-44">
        <SelectField v-model="days" label="Period" :options="WINDOWS" />
      </div>
    </template>
  </PageHeader>

  <div class="space-y-4">
    <NoticeBox data-testid="how-it-works">
      These results come from the quality tool; scoring stays there. They are shown to the person,
      their lead and planners, and to nobody else. There is no ranking and no comparison between
      people.
    </NoticeBox>

    <QualityImportPanel v-if="canImport" />

    <section v-if="canReview" class="space-y-3" aria-labelledby="team-title" aria-live="polite">
      <h2 id="team-title" class="text-base font-semibold text-ink">
        {{ role === 'lead' ? 'Your team' : 'People' }}
      </h2>
      <p v-if="team.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="team.isError.value" tone="danger" data-testid="team-error">
        Could not load the results. {{ problemMessage(team.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="team.data.value?.people.length === 0" data-testid="nobody">
        No quality results in this period.
        <template v-if="canImport">Load a file above.</template>
      </NoticeBox>
      <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
        <table class="w-full text-left text-sm" data-testid="team-table">
          <caption class="sr-only">
            Quality results by person, in employee-number order
          </caption>
          <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
            <tr>
              <th scope="col" class="px-3 py-2 font-medium">Person</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Evaluations</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Average score</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">Latest score</th>
              <th scope="col" class="px-3 py-2 text-right font-medium">CSAT (1 to 5)</th>
              <th scope="col" class="px-3 py-2 font-medium">Coaching due</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in team.data.value?.people"
              :key="p.employeeId"
              class="border-b border-line"
              :data-testid="`row-${p.empNo}`"
            >
              <th scope="row" class="px-3 py-2 font-medium text-ink">
                <button
                  type="button"
                  class="text-left underline decoration-dotted underline-offset-2"
                  :aria-pressed="chosen === p.employeeId"
                  @click="chosen = chosen === p.employeeId ? null : p.employeeId"
                >
                  {{ p.employee }} <span class="font-normal text-ink-muted">({{ p.empNo }})</span>
                </button>
              </th>
              <td class="px-3 py-2 text-right tabular-nums">{{ p.evaluations }}</td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="average">
                {{ scoreText(p.averageScorePct) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="latest">
                {{ scoreText(p.latestScorePct) }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums" data-col="csat">
                {{ p.csatAverage === null ? '—' : p.csatAverage.toFixed(2) }}
              </td>
              <td class="px-3 py-2" data-col="coaching">
                <span
                  v-if="p.coachingIsDue"
                  class="rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn"
                  >Due</span
                >
                {{ coaching(p) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="chosen !== null"
        class="rounded-xl border border-line bg-surface p-4"
        data-testid="person-detail"
      >
        <p v-if="person.isPending.value" class="text-sm text-ink-muted">Loading…</p>
        <NoticeBox v-else-if="person.isError.value" tone="danger">
          Could not load this person. {{ problemMessage(person.error.value) }}
        </NoticeBox>
        <template v-else-if="person.data.value">
          <h3 class="text-sm font-semibold text-ink">
            {{ person.data.value.employee }} ({{ person.data.value.empNo }})
          </h3>
          <ul class="mt-2 divide-y divide-line text-sm" aria-label="Evaluations, newest first">
            <li v-for="(r, i) in person.data.value.results" :key="i" class="flex gap-4 py-1.5">
              <span class="w-24 tabular-nums">{{ r.evaluatedOn }}</span>
              <span class="w-16">{{ KIND_LABEL[r.kind] ?? r.kind }}</span>
              <span class="w-16 text-right font-medium tabular-nums">
                {{ scoreText(r.scorePct) }}
              </span>
              <span class="text-ink-muted">{{ r.csat === null ? '' : `CSAT ${r.csat}` }}</span>
            </li>
          </ul>
        </template>
      </div>
    </section>

    <section class="space-y-2" aria-labelledby="mine-title" aria-live="polite">
      <h2 id="mine-title" class="text-base font-semibold text-ink">My results</h2>
      <p v-if="mine.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="mine.isError.value" data-testid="mine-none">
        {{ problemMessage(mine.error.value) }}
      </NoticeBox>
      <template v-else-if="mine.data.value">
        <NoticeBox v-if="mine.data.value.evaluations === 0" data-testid="mine-empty">
          You have no quality results in this period.
        </NoticeBox>
        <div v-else data-testid="mine">
          <ul class="grid gap-3 sm:grid-cols-3" aria-label="Summary of my results">
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="mine-average">
              <p class="text-xs font-medium text-ink-muted">Average score</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
                {{ scoreText(mine.data.value.averageScorePct) }}
              </p>
              <p class="text-xs text-ink-muted">{{ mine.data.value.evaluations }} evaluations</p>
            </li>
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="mine-csat">
              <p class="text-xs font-medium text-ink-muted">CSAT (1 to 5)</p>
              <p class="mt-1 text-xl font-semibold tabular-nums text-ink">
                {{
                  mine.data.value.csatAverage === null
                    ? '—'
                    : mine.data.value.csatAverage.toFixed(2)
                }}
              </p>
            </li>
            <li class="rounded-xl border border-line bg-surface p-4" data-testid="mine-coaching">
              <p class="text-xs font-medium text-ink-muted">Coaching due</p>
              <p class="mt-1 text-xl font-semibold text-ink">{{ coaching(mine.data.value) }}</p>
            </li>
          </ul>
          <ul
            class="mt-3 divide-y divide-line rounded-xl border border-line bg-surface px-4 text-sm"
            aria-label="My evaluations, newest first"
          >
            <li v-for="(r, i) in mine.data.value.results" :key="i" class="flex gap-4 py-1.5">
              <span class="w-24 tabular-nums">{{ r.evaluatedOn }}</span>
              <span class="w-16">{{ KIND_LABEL[r.kind] ?? r.kind }}</span>
              <span class="w-16 text-right font-medium tabular-nums">
                {{ scoreText(r.scorePct) }}
              </span>
              <span class="text-ink-muted">{{ r.csat === null ? '' : `CSAT ${r.csat}` }}</span>
            </li>
          </ul>
        </div>
      </template>
    </section>
  </div>
</template>
