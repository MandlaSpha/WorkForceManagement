<script setup lang="ts">
import { gapLabel, hours, pct, type UtilisationGroup } from '@/entities/workforce/utilisation'

defineProps<{ caption: string; kind: string; rows: readonly UtilisationGroup[] }>()
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-line bg-surface">
    <table class="w-full text-left text-sm">
      <caption class="sr-only">
        {{
          caption
        }}
      </caption>
      <thead class="text-xs text-ink-muted">
        <tr>
          <th scope="col" class="px-3 py-2">Name</th>
          <th scope="col" class="px-3 py-2">Worked (h)</th>
          <th scope="col" class="px-3 py-2">Billable (h)</th>
          <th scope="col" class="px-3 py-2">Utilisation</th>
          <th scope="col" class="px-3 py-2">Target</th>
          <th scope="col" class="px-3 py-2">Gap</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="r in rows"
          :key="r.key"
          class="border-t border-line"
          :data-testid="`${kind}-${r.key}`"
        >
          <th scope="row" class="px-3 py-2 font-medium text-ink">
            {{ r.name }}
            <span v-if="r.customer" class="font-normal text-ink-muted">({{ r.customer }})</span>
          </th>
          <td class="px-3 py-2">{{ hours(r.workedMin) }}</td>
          <td class="px-3 py-2">{{ hours(r.billableMin) }}</td>
          <td class="px-3 py-2 font-semibold">
            {{ pct(r.utilisationPct) }}
            <div class="relative mt-1 h-1.5 w-28 rounded-full bg-surface-muted" aria-hidden="true">
              <div
                class="h-full rounded-full"
                :class="r.gapPct != null && r.gapPct < 0 ? 'bg-warn' : 'bg-brand'"
                :style="{ width: `${Math.min(100, Math.max(0, r.utilisationPct ?? 0))}%` }"
              ></div>
              <div
                v-if="r.targetPct != null"
                class="absolute -top-0.5 h-2.5 w-0.5 bg-ink"
                :style="{ left: `${Math.min(100, Math.max(0, r.targetPct))}%` }"
              ></div>
            </div>
          </td>
          <td class="px-3 py-2">
            {{ pct(r.targetPct) }}
            <span v-if="r.targetIsDefault" class="text-xs text-ink-muted">(assumed)</span>
          </td>
          <td class="px-3 py-2">
            <span
              v-if="r.gapPct != null"
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="r.gapPct < 0 ? 'bg-warn-soft text-warn' : 'bg-surface-muted text-ink'"
            >
              {{ gapLabel(r.gapPct) }}{{ r.gapPct < 0 ? ' (short)' : '' }}
            </span>
            <span v-else class="text-ink-muted">-</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
