<script setup lang="ts">
import { Users } from 'lucide-vue-next'
import { computed, nextTick, ref } from 'vue'

import {
  sortPeople,
  summaryParts,
  useTeamOverview,
  type TeamPerson,
  type TeamSort,
} from '@/entities/workforce/team'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { formatWeekRange } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TabBar from '@/shared/ui/TabBar.vue'

import TeamCard from './TeamCard.vue'
import TeamDrawer from './TeamDrawer.vue'

const context = useContextStore()
const manager = ref('')
const sort = ref<TeamSort>('az')
const team = useTeamOverview(
  computed(() => context.weekStart),
  computed(() => (manager.value === '' ? null : Number(manager.value))),
)

const SORTS = [
  { key: 'adherence', label: 'Adherence' },
  { key: 'hours', label: 'Hours' },
  { key: 'az', label: 'A-Z' },
] as const

const data = computed(() => team.data.value)
const people = computed(() => sortPeople(data.value?.people ?? [], sort.value))
const sentence = computed(() => (data.value ? summaryParts(data.value.summary) : []))
const managerOptions = computed(() => [
  { value: '', label: 'All teams' },
  ...(data.value?.managers ?? []).map((m) => ({ value: String(m.id), label: m.name })),
])
const count = computed(() => {
  const n = data.value?.summary.headcount ?? 0
  return `${n} ${n === 1 ? 'person' : 'people'} · ${formatWeekRange(context.weekStart)}`
})

const openId = ref<number | null>(null)
const opener = ref<HTMLElement | null>(null)
const open = computed<TeamPerson | null>(
  () => data.value?.people.find((p) => p.employeeId === openId.value) ?? null,
)

function openDrawer(person: TeamPerson): void {
  opener.value = document.activeElement instanceof HTMLElement ? document.activeElement : null
  openId.value = person.employeeId
}
async function closeDrawer(): Promise<void> {
  openId.value = null
  await nextTick()
  opener.value?.focus()
}
</script>

<template>
  <header class="mb-6 mt-4 flex flex-wrap items-end justify-between gap-4">
    <div class="max-w-3xl">
      <p class="flex items-center gap-1.5 text-xs font-medium text-ink-muted" data-testid="caption">
        <Users :size="14" aria-hidden="true" />
        <span>{{ count }}</span>
      </p>
      <h1 class="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Team</h1>
      <p
        v-if="data"
        class="mt-2 max-w-2xl text-sm text-ink-muted sm:text-base"
        data-testid="summary"
      >
        <template v-for="(part, i) in sentence" :key="i">
          <strong v-if="part.bold" class="font-semibold text-ink">{{ part.text }}</strong>
          <template v-else>{{ part.text }}</template>
        </template>
      </p>
    </div>
    <div class="flex flex-wrap items-end gap-3">
      <div v-if="(data?.managers.length ?? 0) > 0" class="w-48">
        <SelectField v-model="manager" label="Team" :options="managerOptions" />
      </div>
      <TabBar
        v-model="sort"
        :tabs="SORTS"
        label="Sort the team by"
        id-prefix="sort"
        :panels="false"
        variant="pill"
      />
    </div>
  </header>

  <section aria-live="polite" :aria-busy="team.isPending.value">
    <div
      v-if="team.isPending.value"
      class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      data-testid="team-loading"
    >
      <div v-for="n in 6" :key="n" class="skeleton h-64"></div>
    </div>
    <NoticeBox v-else-if="team.isError.value" tone="danger" data-testid="team-error">
      Could not load the team. {{ problemMessage(team.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="people.length === 0" data-testid="team-empty">
      Nobody is on this team for this week. People appear here once they report to a team lead.
    </NoticeBox>
    <template v-else>
      <NoticeBox v-if="data && data.summary.withAdherence === 0" data-testid="no-adherence">
        No adherence data has been loaded for this week, so the rings say so instead of showing a
        number. A planner loads it under Operate &gt; Data import.
      </NoticeBox>
      <ul class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="People on the team">
        <TeamCard
          v-for="(person, i) in people"
          :key="person.employeeId"
          :person="person"
          :index="i"
          @open="openDrawer"
        />
      </ul>
    </template>
  </section>

  <TeamDrawer
    v-if="open && data"
    :person="open"
    :threshold-pct="data.adherenceThresholdPct"
    @close="closeDrawer"
  />
</template>
