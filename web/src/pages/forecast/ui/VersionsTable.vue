<script setup lang="ts">
import type { ForecastVersion } from '@/entities/forecast'
import { PublishButton } from '@/features/publish-forecast'
import { RetireButton } from '@/features/retire-forecast'
import { formatDateTime, formatDayLabel } from '@/shared/lib/datetime'

defineProps<{
  versions: ReadonlyArray<ForecastVersion>
  selectedId: string | null
  canPublish: boolean
}>()
const emit = defineEmits<{ select: [id: string] }>()

const BADGE: Record<string, string> = {
  published: 'bg-brand-soft text-brand-ink',
  draft: 'bg-surface-muted text-ink-muted',
  archived: 'bg-surface-muted text-ink-muted line-through',
}
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-line bg-surface">
    <table class="w-full min-w-[44rem] text-left text-sm">
      <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
        Versions
      </caption>
      <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
        <tr>
          <th scope="col" class="px-4 py-2 font-medium">Label</th>
          <th scope="col" class="px-3 py-2 font-medium">Days</th>
          <th scope="col" class="px-3 py-2 text-right font-medium">Intervals</th>
          <th scope="col" class="px-3 py-2 font-medium">Created</th>
          <th scope="col" class="px-3 py-2 font-medium">By</th>
          <th scope="col" class="px-3 py-2 font-medium">Status</th>
          <th scope="col" class="px-4 py-2 text-right font-medium">
            <span class="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="v in versions"
          :key="v.id"
          class="border-b border-line"
          :class="{ 'bg-brand-soft/40': v.id === selectedId }"
        >
          <th scope="row" class="px-4 py-2 font-medium text-ink">{{ v.label || 'No label' }}</th>
          <td class="px-3 py-2">
            {{ formatDayLabel(v.dateFrom) }}
            <template v-if="v.dateTo !== v.dateFrom"> – {{ formatDayLabel(v.dateTo) }}</template>
          </td>
          <td class="px-3 py-2 text-right tabular-nums">{{ v.intervalCount }}</td>
          <td class="px-3 py-2 tabular-nums">{{ formatDateTime(v.createdAt) }}</td>
          <td class="px-3 py-2">{{ v.createdBy }}</td>
          <td class="px-3 py-2">
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold capitalize"
              :class="BADGE[v.status]"
              >{{ v.status }}</span
            >
          </td>
          <td class="px-4 py-2">
            <div class="flex items-center justify-end gap-2">
              <button
                type="button"
                class="text-sm font-medium text-brand-ink underline"
                :aria-label="`View ${v.label || 'forecast'}`"
                :aria-pressed="v.id === selectedId"
                @click="emit('select', v.id)"
              >
                View
              </button>
              <PublishButton v-if="canPublish && v.status === 'draft'" :version="v" />
              <RetireButton v-if="canPublish && v.status !== 'archived'" :version="v" />
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
