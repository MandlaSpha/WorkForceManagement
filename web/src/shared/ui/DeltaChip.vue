<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /** Change since the comparison point. null/undefined = nothing to compare. */
    value: number | null | undefined
    unit?: string
    digits?: number
    /** Which direction is good news: more calls answered is up; more abandons is down. */
    goodWhen?: 'up' | 'down'
    /** Said in words after the change, e.g. "vs last month". */
    versus?: string
  }>(),
  { unit: '%', digits: 1, goodWhen: 'up', versus: '' },
)

const dir = computed(() => {
  const v = props.value
  if (v === null || v === undefined || !Number.isFinite(v)) return 'none'
  const rounded = Number(v.toFixed(props.digits))
  return rounded === 0 ? 'flat' : rounded > 0 ? 'up' : 'down'
})
const tone = computed(() =>
  dir.value === 'up' || dir.value === 'down'
    ? dir.value === props.goodWhen
      ? 'good'
      : 'bad'
    : 'neutral',
)
const amount = computed(() => Math.abs(props.value ?? 0).toFixed(props.digits) + props.unit)
const text = computed(() => {
  if (dir.value === 'none') return 'No comparison'
  if (dir.value === 'flat') return 'No change'
  return `${dir.value === 'up' ? '+' : '−'}${amount.value}`
})
const words = computed(() => {
  const base =
    dir.value === 'up' || dir.value === 'down'
      ? `${dir.value === 'up' ? 'Up' : 'Down'} ${amount.value}`
      : text.value
  return props.versus ? `${base} ${props.versus}` : base
})
const CLASS = {
  good: 'bg-ok-soft text-ok',
  bad: 'bg-danger-soft text-danger',
  neutral: 'bg-surface-muted text-ink-muted',
}
</script>

<template>
  <span
    class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums"
    :class="CLASS[tone]"
    :data-tone="tone"
    data-testid="delta-chip"
  >
    <svg
      v-if="dir === 'up' || dir === 'down'"
      viewBox="0 0 12 12"
      class="size-3"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path :d="dir === 'up' ? 'M6 10V2M2.5 5.5 6 2l3.5 3.5' : 'M6 2v8M2.5 6.5 6 10l3.5-3.5'" />
    </svg>
    <span aria-hidden="true">{{ text }}</span>
    <span class="sr-only">{{ words }}</span>
  </span>
</template>
