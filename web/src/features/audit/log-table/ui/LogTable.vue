<script setup lang="ts">
import type { AuditEvent } from '@/entities/audit-log'
import { formatDateTime } from '@/shared/lib/datetime'

defineProps<{ events: readonly AuditEvent[] }>()

const OUTCOME_TONE: Record<string, string> = {
  success: 'bg-surface-muted text-ink',
  denied: 'bg-warn-soft text-warn',
  failed: 'bg-danger-soft text-danger',
}
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-line bg-surface">
    <table class="w-full min-w-[56rem] text-left text-sm" data-testid="audit-table">
      <caption class="sr-only">
        Audit events, newest first
      </caption>
      <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
        <tr>
          <th scope="col" class="px-4 py-2 font-medium">When</th>
          <th scope="col" class="px-3 py-2 font-medium">Who</th>
          <th scope="col" class="px-3 py-2 font-medium">What</th>
          <th scope="col" class="px-3 py-2 font-medium">Entity</th>
          <th scope="col" class="px-3 py-2 font-medium">Outcome</th>
          <th scope="col" class="px-3 py-2 font-medium">Details</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="e in events"
          :key="e.id"
          class="border-b border-line align-top last:border-0"
          :data-testid="`audit-${e.seq}`"
        >
          <td class="whitespace-nowrap px-4 py-2">{{ formatDateTime(e.occurredAt) }}</td>
          <td class="px-3 py-2">
            {{ e.actor }}
            <span v-if="e.actorRole" class="block text-xs text-ink-muted">{{ e.actorRole }}</span>
          </td>
          <td class="px-3 py-2">
            {{ e.actionLabel }}
            <span class="block text-xs text-ink-muted">{{ e.action }}</span>
          </td>
          <td class="px-3 py-2">
            <template v-if="e.entityType">{{ e.entityType }} {{ e.entityId }}</template>
            <template v-else>–</template>
          </td>
          <td class="px-3 py-2">
            <span
              class="rounded-full px-2 py-0.5 text-xs font-medium"
              :class="OUTCOME_TONE[e.outcome] ?? OUTCOME_TONE.success"
            >
              {{ e.outcome }}
            </span>
          </td>
          <td class="px-3 py-2 text-xs">
            <p v-if="e.reason">{{ e.reason }}</p>
            <ul v-if="e.changes.length" class="mt-1 space-y-0.5">
              <li v-for="(c, i) in e.changes" :key="i">
                <span class="font-medium">{{ c.entityType }} {{ c.entityId }} {{ c.field }}:</span>
                {{ c.old ?? '(not set)' }} → {{ c.new ?? '(not set)' }}
              </li>
            </ul>
            <p v-if="e.requestId" class="mt-1 text-ink-muted">Request {{ e.requestId }}</p>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
