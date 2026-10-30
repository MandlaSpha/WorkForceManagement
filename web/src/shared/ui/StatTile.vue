<script setup lang="ts">
import CountUp from './CountUp.vue'
import DeltaChip from './DeltaChip.vue'
import Sparkline from './Sparkline.vue'

/** A tile for a list: render it inside a `<ul>`. */
const TINTS = {
  brand: 'bg-brand-soft',
  ok: 'bg-ok-soft',
  warn: 'bg-warn-soft',
  danger: 'bg-danger-soft',
} as const

const props = withDefaults(
  defineProps<{
    label: string
    /** A number counts up (formatted with `format`); a string is shown as given. */
    value: number | string
    format?: (n: number) => string
    variant?: 'default' | 'feature'
    /** A soft colour behind a default tile: brand, ok, warn or danger. */
    tint?: 'brand' | 'ok' | 'warn' | 'danger'
    delta?: number | null
    deltaUnit?: string
    deltaGoodWhen?: 'up' | 'down'
    deltaVersus?: string
    /** A real series only. Omit it and no sparkline is drawn. */
    spark?: ReadonlyArray<number | null>
    sparkLabel?: string
  }>(),
  {
    format: undefined,
    variant: 'default',
    tint: undefined,
    delta: undefined,
    deltaUnit: '%',
    deltaGoodWhen: 'up',
    deltaVersus: undefined,
    spark: undefined,
    sparkLabel: undefined,
  },
)
</script>

<template>
  <li
    class="card-lift rounded-xl p-4"
    :class="
      variant === 'feature'
        ? 'bg-brand text-brand-contrast'
        : props.tint
          ? `${TINTS[props.tint]} text-ink`
          : 'border border-line bg-surface text-ink'
    "
  >
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span
          v-if="$slots.icon"
          class="grid size-8 place-items-center rounded-lg"
          :class="variant === 'feature' ? 'bg-white/20' : 'bg-brand-soft text-brand-ink'"
          aria-hidden="true"
        >
          <slot name="icon" />
        </span>
        <p class="text-xs font-medium" :class="variant === 'feature' ? '' : 'text-ink-muted'">
          {{ label }}
        </p>
      </div>
      <DeltaChip
        v-if="delta !== undefined"
        :value="delta"
        :unit="deltaUnit"
        :good-when="deltaGoodWhen"
        :versus="deltaVersus"
      />
    </div>
    <p class="mt-2 text-3xl font-semibold tabular-nums tracking-tight" data-testid="stat-value">
      <CountUp v-if="typeof value === 'number'" :value="value" :format="format" />
      <template v-else>{{ value }}</template>
    </p>
    <p
      v-if="$slots.default"
      class="mt-1 text-xs"
      :class="variant === 'feature' ? '' : 'text-ink-muted'"
    >
      <slot />
    </p>
    <div v-if="spark" class="mt-2">
      <Sparkline
        :values="spark"
        :label="sparkLabel ?? `${label} trend`"
        :tone="variant === 'feature' ? 'current' : 'brand'"
      />
    </div>
  </li>
</template>
