<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { slotName, summarise, usePeaks, type Peaks } from '@/entities/peaks'
import { useContextStore } from '@/features/context-filters'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import { formatDayLabel } from '@/shared/lib/datetime'
import BarSeries, { type BarItem } from '@/shared/ui/BarSeries.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

import PeaksHeat from './PeaksHeat.vue'
import RankedList, { type Ranked } from './RankedList.vue'

const context = useContextStore()
const screen = NAV_ITEMS.find((item) => item.key === 'peaks')

const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Johannesburg' })
const dayBefore = (n: number) =>
  new Date(Date.parse(today) - n * 86_400_000).toISOString().slice(0, 10)

const PRESETS = [
  { key: '7', label: 'Last 7 days', back: 6 },
  { key: '30', label: 'Last 30 days', back: 29 },
  { key: '90', label: 'Last 90 days', back: 89 },
] as const
const choice = ref<string>('30')
const from = ref(dayBefore(29))
const to = ref(today)
watch(choice, (key) => {
  const preset = PRESETS.find((p) => p.key === key)
  if (!preset) return
  from.value = dayBefore(preset.back)
  to.value = today
})

const peaks = usePeaks(
  computed(() => context.queueNumber),
  from,
  to,
)

const data = computed<Peaks | null>(() => peaks.data.value ?? null)
const hasData = computed(() => !!data.value && data.value.daysMeasured > 0)
const summary = computed(() => (data.value ? summarise(data.value) : null))

const calls = (n: number) => `${n.toLocaleString('en-ZA')} ${n === 1 ? 'call' : 'calls'}`
const dec = (s: string) => s // the API already rounds to a tenth

const busiestDay = computed(() => data.value?.busiestDays[0] ?? null)
const quietestDay = computed(() => data.value?.quietestDays[0] ?? null)
const ratioText = computed(() =>
  summary.value?.ratio != null ? `${summary.value.ratio.toFixed(1)}×` : null,
)

// One bar for every calendar day of the range; a day with nothing measured is an empty slot.
const dailyItems = computed<BarItem[]>(() => {
  if (!data.value) return []
  const measured = new Map(data.value.daily.map((d) => [d.day, d.offered]))
  const items: BarItem[] = []
  const end = Date.parse(data.value.dateTo)
  for (let t = Date.parse(data.value.dateFrom); t <= end; t += 86_400_000) {
    const day = new Date(t).toISOString().slice(0, 10)
    const value = measured.get(day) ?? null
    items.push({
      label: String(Number(day.slice(8))),
      title: formatDayLabel(day),
      value,
      tone:
        day === busiestDay.value?.day ? 'high' : day === quietestDay.value?.day ? 'low' : undefined,
      mark:
        value === null
          ? undefined
          : day === busiestDay.value?.day
            ? 'Busiest'
            : day === quietestDay.value?.day
              ? 'Quietest'
              : undefined,
    })
  }
  return items
})
const dailyLabelEvery = computed(() => Math.max(1, Math.ceil(dailyItems.value.length / 10)))

// 48 half-hours; a half-hour that never saw a call is closed and has no bar.
const profileItems = computed<BarItem[]>(() => {
  if (!data.value) return []
  const bySlot = new Map(data.value.profile.map((s) => [s.slot, Number(s.averageOffered)]))
  const values = [...bySlot.values()]
  const top = Math.max(0, ...values)
  const quiet = new Set(data.value.quietestSlots.slice(0, 3).map((s) => s.slot))
  return Array.from({ length: 48 }, (_, i) => {
    const name = slotName(i)
    const value = bySlot.get(name) ?? null
    const busy = value !== null && top > 0 && value >= top * 0.85
    return {
      label: name,
      value,
      tone: busy
        ? ('high' as const)
        : value !== null && quiet.has(name)
          ? ('low' as const)
          : undefined,
      mark: value !== null && value === top ? 'Peak' : undefined,
    }
  })
})

const dayRank = (list: ReadonlyArray<{ day: string; offered: number }>): Ranked[] =>
  list.map((d) => ({
    key: d.day,
    label: formatDayLabel(d.day),
    value: d.offered,
    valueText: calls(d.offered),
  }))
const slotRank = (
  list: ReadonlyArray<{ slot: string; averageOffered: string; days: number }>,
): Ranked[] =>
  list.map((s) => ({
    key: s.slot,
    label: s.slot,
    value: Number(s.averageOffered),
    valueText: `${dec(s.averageOffered)} calls · ${s.days} ${s.days === 1 ? 'day' : 'days'}`,
  }))
const intervalRank = (list: ReadonlyArray<{ start: string; offered: number }>): Ranked[] =>
  list.map((i) => ({
    key: i.start,
    label: `${formatDayLabel(i.start.slice(0, 10))} ${i.start.slice(11)}`,
    value: i.offered,
    valueText: calls(i.offered),
  }))
</script>

<template>
  <PageHeader
    eyebrow="Insight"
    :title="screen?.label ?? 'Peaks & troughs'"
    :subtitle="summary?.sentence && hasData ? summary.sentence : screen?.subtitle"
  />

  <section class="space-y-6" aria-live="polite">
    <div class="flex flex-wrap items-center gap-3">
      <div
        class="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1"
        role="group"
        aria-label="Range"
        data-testid="peaks-range"
      >
        <button
          v-for="p in PRESETS"
          :key="p.key"
          type="button"
          class="press rounded-lg px-3 py-1.5 text-sm"
          :class="
            choice === p.key ? 'bg-brand text-brand-contrast' : 'text-ink hover:bg-surface-muted'
          "
          :aria-pressed="choice === p.key"
          @click="choice = p.key"
        >
          {{ p.label }}
        </button>
        <button
          type="button"
          class="press rounded-lg px-3 py-1.5 text-sm"
          :class="
            choice === 'custom' ? 'bg-brand text-brand-contrast' : 'text-ink hover:bg-surface-muted'
          "
          :aria-pressed="choice === 'custom'"
          @click="choice = 'custom'"
        >
          Custom
        </button>
      </div>
      <template v-if="choice === 'custom'">
        <label class="flex items-center gap-2 text-sm text-ink">
          From
          <input
            v-model="from"
            type="date"
            class="rounded-lg border border-line bg-surface px-2 py-1"
          />
        </label>
        <label class="flex items-center gap-2 text-sm text-ink">
          To
          <input
            v-model="to"
            type="date"
            class="rounded-lg border border-line bg-surface px-2 py-1"
          />
        </label>
      </template>
    </div>

    <NoticeBox v-if="context.queueNumber === null">
      Choose a queue at the top of the page. Queues appear once call data has been imported.
    </NoticeBox>
    <NoticeBox v-else-if="from > to" tone="warn">The start date is after the end date.</NoticeBox>
    <div v-else-if="peaks.isPending.value" class="space-y-4" data-testid="peaks-loading">
      <span class="sr-only">Loading…</span>
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div v-for="n in 5" :key="n" class="skeleton h-24"></div>
      </div>
      <div class="skeleton h-48"></div>
      <div class="skeleton h-48"></div>
    </div>
    <NoticeBox v-else-if="peaks.isError.value" tone="danger" data-testid="peaks-error">
      Could not work out peaks. {{ problemMessage(peaks.error.value) }}
    </NoticeBox>

    <template v-else-if="data">
      <NoticeBox v-if="!hasData" data-testid="peaks-none">
        No calls were measured in that range, so there is nothing to rank.
      </NoticeBox>
      <template v-else>
        <ul class="page-enter grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="peaks-tiles">
          <StatTile
            variant="feature"
            label="Busiest day"
            :value="busiestDay ? formatDayLabel(busiestDay.day) : '–'"
          >
            {{ busiestDay ? calls(busiestDay.offered) : '' }}
          </StatTile>
          <StatTile
            label="Quietest day"
            :value="quietestDay ? formatDayLabel(quietestDay.day) : '–'"
          >
            {{ quietestDay ? calls(quietestDay.offered) : '' }}
          </StatTile>
          <StatTile label="Busiest half-hour" :value="summary?.busiestSlot?.slot ?? '–'">
            {{
              summary?.busiestSlot
                ? `${summary.busiestSlot.average.toFixed(1)} calls on average`
                : ''
            }}
          </StatTile>
          <StatTile label="Peak to trough" :value="ratioText ?? '–'">
            {{
              ratioText
                ? `Busiest ÷ quietest open half-hour`
                : 'Needs two open half-hours with calls'
            }}
          </StatTile>
          <StatTile label="Days measured" :value="data.daysMeasured">
            Days with no data are not counted as quiet
          </StatTile>
        </ul>

        <section
          class="page-enter rounded-2xl border border-line bg-surface p-4 shadow-card"
          aria-labelledby="peaks-daily-title"
          data-testid="peaks-daily"
        >
          <h2 id="peaks-daily-title" class="text-sm font-semibold text-ink">Calls each day</h2>
          <div class="mt-3 overflow-x-auto">
            <div class="min-w-[36rem] pt-4">
              <BarSeries
                :items="dailyItems"
                value-label="Calls offered"
                :label-every="dailyLabelEvery"
                :summary="`Calls offered each day. Busiest ${busiestDay ? `${busiestDay.day}, ${calls(busiestDay.offered)}` : 'none'}; quietest ${quietestDay ? `${quietestDay.day}, ${calls(quietestDay.offered)}` : 'none'}.`"
              />
            </div>
          </div>
        </section>

        <section
          class="page-enter rounded-2xl border border-line bg-surface p-4 shadow-card"
          aria-labelledby="peaks-profile-title"
          data-testid="peaks-profile"
        >
          <h2 id="peaks-profile-title" class="text-sm font-semibold text-ink">
            Average calls by half-hour of the day
          </h2>
          <div class="mt-3 overflow-x-auto">
            <div class="min-w-[44rem] pt-4">
              <BarSeries
                :items="profileItems"
                value-label="Average calls offered"
                :label-every="4"
                :format="(n) => n.toFixed(1)"
                :summary="`Average calls in each half-hour. Busiest ${summary?.busiestSlot?.slot ?? 'none'}; quietest open ${summary?.quietestSlot?.slot ?? 'none'}.`"
              />
            </div>
          </div>
        </section>

        <div class="page-enter">
          <PeaksHeat :cells="data.heat" />
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <RankedList
            title="Busiest days"
            testid="busiest-days"
            :items="dayRank(data.busiestDays)"
          />
          <RankedList
            title="Quietest days"
            testid="quietest-days"
            :items="dayRank(data.quietestDays)"
          />
          <RankedList
            title="Busiest half-hours (average a day)"
            testid="busiest-slots"
            :items="slotRank(data.busiestSlots)"
          />
          <RankedList
            title="Quietest half-hours while open (average a day)"
            testid="quietest-slots"
            :items="slotRank(data.quietestSlots)"
          />
          <div class="md:col-span-2">
            <RankedList
              title="Single busiest half-hours"
              testid="busiest-intervals"
              :items="intervalRank(data.busiestIntervals)"
            />
          </div>
        </div>
      </template>
    </template>
  </section>
</template>
