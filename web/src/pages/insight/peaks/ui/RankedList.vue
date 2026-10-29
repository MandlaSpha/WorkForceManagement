<script setup lang="ts">
import { computed } from 'vue'

export interface Ranked {
  key: string
  label: string
  value: number
  valueText: string
}

const props = defineProps<{ title: string; items: ReadonlyArray<Ranked>; testid: string }>()
const id = `rank-${props.testid}`
const top = computed(() => Math.max(1, ...props.items.map((x) => x.value)))
</script>

<template>
  <section class="rounded-2xl border border-line bg-surface p-4 shadow-card" :aria-labelledby="id">
    <h2 :id="id" class="text-sm font-semibold text-ink">{{ title }}</h2>
    <ol class="mt-3 space-y-3" :data-testid="testid">
      <li
        v-for="(item, i) in items"
        :key="item.key"
        class="grid grid-cols-[1.75rem_1fr] items-center gap-x-3"
      >
        <span
          class="grid size-7 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand-ink"
          >{{ i + 1 }}</span
        >
        <div class="min-w-0">
          <p class="flex flex-wrap justify-between gap-x-2 text-sm text-ink">
            <span class="font-medium">{{ item.label }}</span>
            <span class="tabular-nums text-ink-muted">{{ item.valueText }}</span>
          </p>
          <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
            <div
              class="stacked-seg h-full rounded-full bg-chart-1"
              :style="{ width: `${(item.value / top) * 100}%` }"
            ></div>
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>
