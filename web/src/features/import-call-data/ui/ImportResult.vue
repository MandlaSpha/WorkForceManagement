<script setup lang="ts">
import { computed } from 'vue'

import { formatCount, type ImportReport } from '@/entities/call-data'
import { formatDate } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { describeReason } from '../model/messages'

const props = defineProps<{ report: ImportReport }>()

const counts = computed(() => [
  { label: 'Rows read', value: props.report.rowsRead },
  { label: 'Calls added', value: props.report.rowsInserted },
  { label: 'Already imported', value: props.report.rowsDuplicate },
  { label: 'Rows skipped', value: props.report.rowsRejected },
])
const rejected = computed(() => Object.entries(props.report.rejectedSummary))
const warnings = computed(() => Object.entries(props.report.warnings))
</script>

<template>
  <section class="space-y-4" aria-labelledby="import-result-title">
    <h2 id="import-result-title" class="text-base font-semibold text-ink">
      Imported {{ report.fileName }}
    </h2>
    <p class="text-sm text-ink-muted">
      Calls from {{ formatDate(report.periodStart) }} to {{ formatDate(report.periodEnd) }} (times
      read as {{ report.sourceTimezone }}).
    </p>

    <NoticeBox v-if="report.reconciles" data-testid="reconciles">
      <strong>Reconciles.</strong> The stored calls and the 30-minute intervals agree with the file
      in three independent calculations.
    </NoticeBox>
    <NoticeBox v-else tone="danger" data-testid="does-not-reconcile">
      <strong>Does not reconcile.</strong> The stored figures differ from the file. Do not rely on
      them; tell the development team.
    </NoticeBox>

    <dl class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div v-for="count in counts" :key="count.label" class="rounded-xl border border-line p-3">
        <dt class="text-xs text-ink-muted">{{ count.label }}</dt>
        <dd class="text-xl font-semibold tabular-nums text-ink">{{ formatCount(count.value) }}</dd>
      </div>
    </dl>

    <NoticeBox v-if="rejected.length > 0" tone="warn">
      <p class="font-medium">Rows that were skipped</p>
      <ul class="mt-1 list-disc pl-5">
        <li v-for="[code, count] in rejected" :key="code">
          {{ formatCount(count) }} with {{ describeReason(code) }}
        </li>
      </ul>
    </NoticeBox>

    <NoticeBox v-if="warnings.length > 0" tone="warn">
      <p class="font-medium">Calls kept, with one value ignored</p>
      <ul class="mt-1 list-disc pl-5">
        <li v-for="[code, count] in warnings" :key="code">
          {{ formatCount(count) }} with {{ describeReason(code) }}
        </li>
      </ul>
    </NoticeBox>

    <div v-if="report.sheets.length > 0" data-testid="sheet-report">
      <h3 class="text-sm font-semibold text-ink">Sheets in the file</h3>
      <table class="mt-1 w-full text-left text-sm">
        <thead class="text-xs text-ink-muted">
          <tr>
            <th scope="col" class="py-1 pr-3 font-medium">Sheet</th>
            <th scope="col" class="py-1 pr-3 font-medium">Read</th>
            <th scope="col" class="py-1 pr-3 text-right font-medium">Rows read</th>
            <th scope="col" class="py-1 pr-3 text-right font-medium">Rows kept</th>
            <th scope="col" class="py-1 font-medium">Warnings</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sheet in report.sheets" :key="sheet.sheet" class="border-t border-line">
            <th scope="row" class="py-1 pr-3 font-normal text-ink">{{ sheet.sheet }}</th>
            <td class="py-1 pr-3">{{ sheet.read ? 'Yes' : 'No' }}</td>
            <td class="py-1 pr-3 text-right tabular-nums">{{ formatCount(sheet.rowsRead) }}</td>
            <td class="py-1 pr-3 text-right tabular-nums">{{ formatCount(sheet.rowsKept) }}</td>
            <td class="py-1 text-xs text-ink-muted">
              <span v-if="Object.keys(sheet.warnings).length === 0">None</span>
              <span
                v-for="[code, count] in Object.entries(sheet.warnings)"
                :key="code"
                class="block"
              >
                {{ formatCount(count) }} {{ describeReason(code) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
