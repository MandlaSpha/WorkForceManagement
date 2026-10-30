<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import {
  COVER_STATUS_LABEL,
  SCENARIO_LABEL,
  WORK_MODE_LABEL,
  useMobilise,
  type Scenario,
} from '@/entities/workforce/continuity'
import { BackupTeamsPanel } from '@/features/continuity/manage-teams'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

const context = useContextStore()
const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'continuity')

// A roster covers working days: from a weekend the page opens on the Friday before, the last day
// that has one.
function lastWorkingDay(iso: string): string {
  const at = new Date(`${iso}T12:00:00Z`)
  const back = { 6: 1, 0: 2 }[at.getUTCDay()] ?? 0
  return new Date(at.getTime() - back * 86_400_000).toISOString().slice(0, 10)
}
const day = ref(lastWorkingDay(todayInJohannesburg()))
const scenario = ref<Scenario>('site')
const lostText = ref('30')
const lostPct = computed(() => {
  const n = Number(lostText.value)
  return Number.isInteger(n) && n >= 0 && n <= 100 ? n : 30
})
const queueId = computed(() => context.queueNumber)
const mobilise = useMobilise(queueId, day, scenario, lostPct)

// Cosmetic: the API refuses writes from anyone but a planner or admin.
const canEdit = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const scenarioOptions = (Object.keys(SCENARIO_LABEL) as Scenario[]).map((value) => ({
  value,
  label: SCENARIO_LABEL[value],
}))
const pct = (v: number | null) => (v === null ? '-' : `${v.toFixed(1)}%`)
</script>

<template>
  <PageHeader
    eyebrow="Operate"
    :title="screen?.label ?? 'Continuity'"
    :subtitle="screen?.subtitle"
  />

  <div class="space-y-6">
    <NoticeBox v-if="queueId === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>

    <template v-else>
      <section class="space-y-4" aria-labelledby="mobilise-title">
        <h2 id="mobilise-title" class="text-base font-semibold text-ink">Mobilise</h2>
        <div class="grid gap-3 sm:grid-cols-3">
          <TextField v-model="day" label="Day" type="date" />
          <SelectField
            :model-value="scenario"
            label="What happened"
            :options="scenarioOptions"
            @update:model-value="scenario = $event as Scenario"
          />
          <TextField
            v-if="scenario === 'outbreak'"
            v-model="lostText"
            label="Share of the roster lost (%)"
            type="number"
            :min="0"
            :max="100"
          />
        </div>

        <p v-if="mobilise.isPending.value" class="text-sm text-ink-muted">Loading…</p>
        <NoticeBox v-else-if="mobilise.isError.value" tone="danger" data-testid="mobilise-error">
          Could not work out the cover. {{ problemMessage(mobilise.error.value) }}
        </NoticeBox>
        <div v-else-if="mobilise.data.value" class="space-y-4" aria-live="polite">
          <ul
            class="grid grid-cols-2 gap-3 lg:grid-cols-4"
            aria-label="Impact"
            data-testid="impact"
          >
            <StatTile
              label="On the published roster"
              :value="mobilise.data.value.impact.rostered"
              tint="brand"
              data-testid="rostered"
            />
            <StatTile
              label="Lost"
              :value="mobilise.data.value.impact.lost"
              tint="danger"
              data-testid="lost"
            />
            <StatTile
              label="Covered by backups"
              :value="mobilise.data.value.impact.recovered"
              tint="ok"
              data-testid="recovered"
            />
            <StatTile
              label="Roster after (still short by)"
              :value="pct(mobilise.data.value.impact.coveragePct)"
              :tint="mobilise.data.value.impact.shortfall > 0 ? 'warn' : 'ok'"
              data-testid="after"
            >
              <span
                :class="mobilise.data.value.impact.shortfall > 0 ? 'text-danger' : 'text-ok'"
                data-testid="shortfall"
              >
                ({{ mobilise.data.value.impact.shortfall }})
              </span>
            </StatTile>
          </ul>

          <NoticeBox v-if="mobilise.data.value.teams.length === 0" data-testid="no-cover">
            No backup team is named for this queue, so nobody can be called on.
          </NoticeBox>
          <ul v-else class="grid gap-3 md:grid-cols-2" aria-label="Backup cover">
            <li
              v-for="t in mobilise.data.value.teams"
              :key="t.teamId"
              class="space-y-2 rounded-xl border border-line bg-surface p-4"
              :data-testid="`cover-${t.name}`"
            >
              <h3 class="text-sm font-semibold text-ink">
                {{ t.name }}
                <span class="font-normal text-ink-muted">
                  ({{ t.usableCount }} of {{ t.memberCount }} can cover)
                </span>
              </h3>
              <p v-if="t.candidates.length === 0" class="text-xs text-ink-muted">
                Names are shown to planners, admins and team leads only.
              </p>
              <ul class="space-y-2">
                <li
                  v-for="c in t.candidates"
                  :key="c.employeeId"
                  class="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
                  :data-testid="`cand-${c.empNo}`"
                >
                  <span class="min-w-0 flex-1">
                    {{ c.employee }} <span class="text-ink-muted">({{ c.empNo }})</span>
                  </span>
                  <span class="text-xs text-ink-muted">
                    {{ WORK_MODE_LABEL[c.workMode] ?? c.workMode }}
                  </span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    :class="c.usable ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn'"
                  >
                    {{ COVER_STATUS_LABEL[c.status] ?? c.status }}
                  </span>
                </li>
              </ul>
            </li>
          </ul>
        </div>
      </section>

      <BackupTeamsPanel :queue-id="queueId" :can-edit="canEdit" />
    </template>
  </div>
</template>
