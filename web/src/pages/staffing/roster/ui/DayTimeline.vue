<script setup lang="ts">
import { computed } from 'vue'

import { SHIFT_TONE, type Roster, type ShiftActivity } from '@/entities/scheduling'
import { formatDayLabel } from '@/shared/lib/datetime'

const props = defineProps<{
  roster: Roster
  day: string
  activities: ReadonlyArray<ShiftActivity>
  /** Minutes since midnight in South African time, only when `day` is today. */
  nowMin: number | null
}>()
const emit = defineEmits<{ 'update:day': [day: string] }>()

const minutes = (hhmm: string): number => {
  const [h, m] = hhmm.split(':').map(Number)
  return (h ?? 0) * 60 + (m ?? 0)
}
const clock = (min: number): string =>
  `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`

const shiftById = computed(() => new Map(props.roster.shifts.map((s) => [s.id, s])))

interface Bar {
  employeeId: number
  name: string
  empNo: string
  code: string
  kind: string
  start: number
  end: number
  away: Array<{ kind: string; start: number; end: number }>
}

const bars = computed<Bar[]>(() =>
  props.roster.rows.flatMap((row) => {
    const cell = row.cells.find((c) => c.day === props.day)
    const shift = cell ? shiftById.value.get(cell.shiftId) : undefined
    if (!shift) return []
    const start = minutes(shift.startTime)
    // A night shift is drawn to midnight; its tail belongs to the next day's picture.
    const end =
      shift.overnight || minutes(shift.endTime) <= start ? 24 * 60 : minutes(shift.endTime)
    return {
      employeeId: row.employeeId,
      name: row.name,
      empNo: row.empNo,
      code: shift.code,
      kind: shift.kind,
      start,
      end,
      away: props.activities
        .filter((a) => a.employeeId === row.employeeId && a.day === props.day)
        .map((a) => ({ kind: a.kind, start: minutes(a.startTime), end: minutes(a.endTime) })),
    }
  }),
)
const off = computed(() => props.roster.rows.length - bars.value.length)

// The axis covers the hours anyone works, to the whole hour, and never less than eight of them.
const span = computed(() => {
  if (bars.value.length === 0) return { from: 7 * 60, to: 17 * 60 }
  let from = Math.floor(Math.min(...bars.value.map((b) => b.start)) / 60) * 60
  let to = Math.ceil(Math.max(...bars.value.map((b) => b.end)) / 60) * 60
  if (to - from < 8 * 60) to = Math.min(24 * 60, from + 8 * 60)
  if (to - from < 8 * 60) from = Math.max(0, to - 8 * 60)
  return { from, to }
})
const pct = (min: number): number =>
  ((Math.min(Math.max(min, span.value.from), span.value.to) - span.value.from) /
    (span.value.to - span.value.from)) *
  100
const ticks = computed(() => {
  const out: number[] = []
  for (let m = span.value.from; m <= span.value.to; m += 60) out.push(m)
  return out
})
const now = computed(() =>
  props.nowMin !== null && props.nowMin >= span.value.from && props.nowMin <= span.value.to
    ? pct(props.nowMin)
    : null,
)
const onNow = computed(() =>
  props.nowMin === null
    ? null
    : bars.value.filter((b) => b.start <= (props.nowMin ?? 0) && (props.nowMin ?? 0) < b.end)
        .length,
)

const AWAY_LABEL: Record<string, string> = {
  break: 'Break',
  lunch: 'Lunch',
  training: 'Training',
  meeting: 'Meeting',
  coaching: 'Coaching',
  other: 'Other',
}
</script>

<template>
  <section
    class="rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
    aria-labelledby="timeline-title"
    data-testid="day-timeline"
  >
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 id="timeline-title" class="text-base font-semibold text-ink">
          {{ formatDayLabel(day) }}
        </h2>
        <p class="text-sm text-ink-muted" data-testid="timeline-count">
          {{ bars.length }} on shift<template v-if="onNow !== null"> · {{ onNow }} on now</template
          ><template v-if="off > 0"> · {{ off }} off</template>
        </p>
      </div>
      <div class="inline-flex flex-wrap gap-1" role="group" aria-label="Day">
        <button
          v-for="d in roster.days"
          :key="d"
          type="button"
          class="press min-h-9 rounded-lg px-2.5 text-xs"
          :class="d === day ? 'bg-brand text-brand-contrast' : 'bg-surface-muted text-ink'"
          :aria-pressed="d === day"
          :data-testid="`timeline-day-${d}`"
          @click="emit('update:day', d)"
        >
          {{ formatDayLabel(d) }}
        </button>
      </div>
    </div>

    <p v-if="bars.length === 0" class="mt-4 text-sm text-ink-muted" data-testid="timeline-empty">
      Nobody is rostered on this day.
    </p>
    <div v-else class="mt-4 overflow-x-auto">
      <div class="min-w-[40rem]">
        <div class="grid grid-cols-[9rem_1fr] items-end gap-3 text-xs text-ink-muted">
          <span>{{ bars.length }} on the floor</span>
          <div class="relative h-5" aria-hidden="true">
            <span
              v-for="t in ticks"
              :key="t"
              class="absolute -translate-x-1/2 tabular-nums"
              :style="{ left: `${pct(t)}%` }"
              >{{ clock(t) }}</span
            >
          </div>
        </div>

        <div class="relative">
          <div
            v-if="now !== null"
            class="pointer-events-none absolute inset-y-0 z-10 w-px bg-danger"
            :style="{ left: `calc(9rem + 0.75rem + (100% - 9rem - 0.75rem) * ${now / 100})` }"
            aria-hidden="true"
            data-testid="timeline-now"
          ></div>
          <ul class="mt-1 divide-y divide-line">
            <li
              v-for="b in bars"
              :key="b.employeeId"
              class="grid grid-cols-[9rem_1fr] items-center gap-3 py-1.5"
              :data-testid="`timeline-row-${b.empNo}`"
            >
              <span class="min-w-0">
                <span class="block truncate text-sm font-medium text-ink" :title="b.empNo">{{
                  b.name
                }}</span>
              </span>
              <div class="relative h-9">
                <div
                  v-for="t in ticks"
                  :key="t"
                  class="absolute inset-y-0 border-l border-dashed border-line"
                  :style="{ left: `${pct(t)}%` }"
                  aria-hidden="true"
                ></div>
                <div
                  class="absolute inset-y-1 overflow-hidden rounded-lg px-2 text-xs font-semibold leading-7"
                  :class="SHIFT_TONE[b.kind] ?? 'bg-surface-muted text-ink'"
                  :style="{ left: `${pct(b.start)}%`, width: `${pct(b.end) - pct(b.start)}%` }"
                  :title="`${b.code} ${clock(b.start)} to ${clock(b.end)}`"
                  data-testid="timeline-bar"
                >
                  {{ b.code }}
                  <span class="font-normal opacity-80"
                    >{{ clock(b.start) }}–{{ clock(b.end) }}</span
                  >
                  <span
                    v-for="(a, i) in b.away"
                    :key="i"
                    class="absolute inset-y-0 bg-ink/25"
                    :style="{
                      left: `${((a.start - b.start) / (b.end - b.start)) * 100}%`,
                      width: `${((a.end - a.start) / (b.end - b.start)) * 100}%`,
                    }"
                    :title="`${AWAY_LABEL[a.kind] ?? a.kind} ${clock(a.start)}–${clock(a.end)}`"
                    data-testid="timeline-away"
                  ></span>
                </div>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>
