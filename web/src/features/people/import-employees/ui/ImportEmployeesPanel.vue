<script setup lang="ts">
import { computed, ref } from 'vue'

import { importReason } from '@/entities/scheduling'
import type { EmployeeImportReport } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useImportEmployees } from '../model/useImportEmployees'

const file = ref<File | null>(null)
const { check, run } = useImportEmployees()

// What the planner is looking at: the preview of the chosen file, then the real result.
const report = computed<EmployeeImportReport | null>(
  () => run.data.value ?? check.data.value ?? null,
)
const failure = computed(() =>
  run.isError.value ? run.error.value : check.isError.value ? check.error.value : null,
)
const rejectedTotal = computed(() =>
  Object.values(report.value?.rejected ?? {}).reduce((sum, n) => sum + n, 0),
)

function choose(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  check.reset()
  run.reset()
}
function preview(): void {
  if (file.value) check.mutate(file.value)
}
function confirm(): void {
  if (file.value) run.mutate(file.value)
}
</script>

<template>
  <section class="space-y-3" aria-labelledby="emp-import-title">
    <h2 id="emp-import-title" class="text-base font-semibold text-ink">Bring in employees</h2>
    <p class="text-sm text-ink-muted">
      A CSV or Excel file with a row per person and a header row. Needed:
      <code>Employee No</code> and <code>Name</code>. Optional: <code>Contract</code> (permanent or
      seasonal), <code>Weekly Hours</code>, <code>Work Mode</code> (office, remote, hybrid),
      <code>Start Date</code>, <code>End Date</code>, <code>Manager</code> (an employee number),
      <code>Queues</code> (for example <code>TotalSA;Gijima:2</code>, a skill level after a colon)
      and <code>ACD Logins</code> (separated by semicolons). People already known are updated; a
      blank cell changes nothing. Any other column is ignored and never stored. Check the file
      first: it changes nothing until you confirm.
    </p>
    <form class="space-y-3" aria-label="Import employees" @submit.prevent="preview">
      <div>
        <label for="emp-file" class="block text-xs font-medium text-ink-muted">
          Employees (.csv or .xlsx)
        </label>
        <input
          id="emp-file"
          type="file"
          accept=".csv,.xlsx,text/csv"
          class="mt-1 block text-sm text-ink"
          @change="choose"
        />
      </div>
      <AppButton type="submit" :loading="check.isPending.value" :disabled="file === null">
        Check the file
      </AppButton>
    </form>

    <NoticeBox v-if="failure" tone="danger" data-testid="emp-import-error">
      <p class="font-medium">Nothing was imported.</p>
      <p>{{ problemMessage(failure) }}</p>
    </NoticeBox>

    <div v-if="report" class="space-y-2" data-testid="emp-import-report">
      <p class="text-sm text-ink">
        {{ report.dryRun ? 'If you import this file:' : 'Imported:' }}
        <strong>{{ report.created }}</strong> added, <strong>{{ report.updated }}</strong> updated,
        <strong>{{ report.unchanged }}</strong> already up to date,
        <strong>{{ report.loginsMapped }}</strong> ACD logins tied to people.
      </p>
      <NoticeBox v-if="rejectedTotal > 0" tone="warn" data-testid="emp-import-rejected">
        <p class="font-medium">{{ rejectedTotal }} rows are not kept:</p>
        <ul class="list-disc pl-5">
          <li v-for="(count, reason) in report.rejected" :key="reason">
            {{ count }} with {{ importReason(reason) }}
          </li>
        </ul>
      </NoticeBox>
      <NoticeBox v-if="report.ignoredColumns.length > 0" data-testid="emp-import-ignored">
        Not read, and not stored: {{ report.ignoredColumns.join(', ') }}.
      </NoticeBox>
      <AppButton
        v-if="report.dryRun"
        :loading="run.isPending.value"
        :disabled="report.created + report.updated + report.loginsMapped === 0"
        @click="confirm"
      >
        Import these
      </AppButton>
    </div>
  </section>
</template>
