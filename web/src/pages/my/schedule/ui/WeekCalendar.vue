<script setup lang="ts">
import { computed } from 'vue'

import { clock } from '@/entities/availability'
import {
  hoursLabel,
  overlapColumns,
  paidHours,
  positionOf,
  shiftKind,
  weekSegments,
} from '@/entities/my-schedule'
import type { MyShift, ShiftKind } from '@/entities/my-schedule'
import { addDays } from '@/shared/lib/week'

const props = defineProps<{
  /** Monday of the week shown. */
  weekStart: string
  /** Shifts from the day before the week to its last day, so a Sunday-night tail shows on Monday. */
  shifts: MyShift[]
  today: string
  /** Now in Africa/Johannesburg, minutes since midnight. */
  nowMinutes: number
}>()

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const HOURS = Array.from({ length: 24 }, (_, h) => h)
const days = computed(() => DAYS.map((name, i) => ({ name, iso: addDays(props.weekStart, i) })))

const KIND_CLASS: Record<ShiftKind, string> = {
  early: 'bg-ok-soft text-ok border-ok',
  day: 'bg-brand-soft text-brand-ink border-brand',
  late: 'bg-warn-soft text-warn border-warn',
  night: 'bg-side text-on-side border-side-line',
}
const KIND_LABEL: Record<ShiftKind, string> = {
  early: 'Early',
  day: 'Day',
  late: 'Late',
  night: 'Night',
}

const blocks = computed(() => {
  const segments = weekSegments(props.shifts, props.weekStart)
  let order = 0
  return days.value.map((d) => {
    const placed = overlapColumns(segments.filter((s) => s.day === d.iso))
    return placed.map((p) => ({
      key: `${p.item.day}-${p.item.shift.shift}-${p.item.startMin}`,
      seg: p.item,
      pos: positionOf(p.item.startMin, p.item.endMin),
      left: (p.column / p.columns) * 100,
      width: 100 / p.columns,
      order: order++,
      kind: shiftKind(p.item.shift),
    }))
  })
})

const label = (shift: MyShift) =>
  `${shift.shift}, ${KIND_LABEL[shiftKind(shift)]} shift, ${clock(shift.startTime)} to ${clock(shift.endTime)}, ${hoursLabel(paidHours(shift))} paid`
</script>

<template>
  <div
    class="overflow-x-auto rounded-3xl bg-surface p-3 shadow-[var(--shadow-card)]"
    data-testid="week-grid"
    role="region"
    aria-label="Week calendar"
    tabindex="0"
  >
    <div class="min-w-[44rem]">
      <div class="grid grid-cols-[3rem_repeat(7,minmax(0,1fr))] text-xs text-ink-muted">
        <div />
        <div
          v-for="d in days"
          :key="d.iso"
          class="pb-2 text-center font-medium"
          :class="d.iso === today ? 'text-brand-ink' : ''"
        >
          <time :datetime="d.iso">{{ d.name }} {{ Number(d.iso.slice(8)) }}</time>
        </div>
      </div>

      <div
        class="quiet-scroll grid max-h-[34rem] grid-cols-[3rem_repeat(7,minmax(0,1fr))] overflow-y-auto"
        role="region"
        aria-label="Hours of the week"
        tabindex="0"
      >
        <div class="relative h-[48rem]" aria-hidden="true">
          <span
            v-for="h in HOURS"
            :key="h"
            class="absolute right-2 -translate-y-1/2 text-[10px] tabular-nums text-ink-muted"
            :style="{ top: `${(h / 24) * 100}%` }"
          >
            {{ h === 0 ? '' : String(h).padStart(2, '0') + ':00' }}
          </span>
        </div>

        <div
          v-for="(col, i) in blocks"
          :key="days[i]!.iso"
          class="relative h-[48rem] border-l border-line"
          :class="days[i]!.iso === today ? 'bg-brand-soft/30' : ''"
          :data-testid="`week-day-${days[i]!.iso}`"
        >
          <span
            v-for="h in HOURS"
            :key="h"
            class="absolute inset-x-0 border-t border-line/60"
            :style="{ top: `${(h / 24) * 100}%` }"
            aria-hidden="true"
          />
          <div
            v-for="b in col"
            :key="b.key"
            class="week-block group absolute z-10 rounded-xl border-l-4 px-1.5 py-1 text-[11px] leading-tight outline-none focus-visible:ring-2 focus-visible:ring-brand"
            :class="KIND_CLASS[b.kind]"
            :style="{
              top: `${b.pos.top}%`,
              height: `${b.pos.height}%`,
              left: `calc(${b.left}% + 2px)`,
              width: `calc(${b.width}% - 4px)`,
              animationDelay: `${Math.min(b.order, 14) * 45}ms`,
            }"
            tabindex="0"
            role="group"
            :aria-label="label(b.seg.shift)"
            data-testid="week-block"
          >
            <span class="block font-semibold">{{ b.seg.shift.shift }}</span>
            <span class="block tabular-nums">
              {{ clock(b.seg.shift.startTime) }}-{{ clock(b.seg.shift.endTime) }}
            </span>
            <span
              class="pointer-events-none invisible absolute left-1/2 top-1 z-20 w-44 -translate-x-1/2 rounded-xl bg-side px-3 py-2 text-xs text-on-side opacity-0 shadow-[var(--shadow-pop)] transition-opacity group-hover:visible group-hover:opacity-100 group-focus-visible:visible group-focus-visible:opacity-100"
              role="tooltip"
            >
              <span class="block font-semibold">{{ b.seg.shift.shift }}</span>
              <span class="block tabular-nums">
                {{ clock(b.seg.shift.startTime) }} to {{ clock(b.seg.shift.endTime) }}
              </span>
              <span class="block">{{ hoursLabel(paidHours(b.seg.shift)) }} paid</span>
              <span class="block text-side-dim">{{ b.seg.shift.queue }}</span>
            </span>
          </div>
          <span
            v-if="days[i]!.iso === today"
            class="pointer-events-none absolute inset-x-0 z-20 border-t-2 border-danger"
            :style="{ top: `${(nowMinutes / 1440) * 100}%` }"
            data-testid="now-marker"
            aria-hidden="true"
          >
            <span class="absolute -left-1 -top-1.5 size-2.5 rounded-full bg-danger" />
          </span>
        </div>
      </div>
    </div>

    <p class="mt-2 flex flex-wrap gap-3 text-[11px] text-ink-muted" aria-label="Colour key">
      <span v-for="(text, kind) in KIND_LABEL" :key="kind" class="inline-flex items-center gap-1">
        <span class="size-2.5 rounded-sm border-l-4" :class="KIND_CLASS[kind]" />{{ label }}
      </span>
    </p>
  </div>
</template>

<style scoped>
@keyframes week-block-in {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.week-block {
  animation: week-block-in 320ms ease-out both;
}
@media (prefers-reduced-motion: reduce) {
  .week-block {
    animation: none;
  }
}
</style>
