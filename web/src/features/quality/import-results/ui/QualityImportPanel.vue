<script setup lang="ts">
import { ref, useId } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useImportQuality } from '../model/useImportQuality'

const inputId = useId()
const file = ref<File | null>(null)
const picker = ref<HTMLInputElement | null>(null)
const importQuality = useImportQuality()

function choose(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  importQuality.reset()
}

function submit(): void {
  if (!file.value) return
  importQuality.mutate(file.value, {
    onSuccess: () => {
      file.value = null
      if (picker.value) picker.value.value = ''
    },
  })
}
</script>

<template>
  <section
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    aria-labelledby="quality-up-title"
  >
    <h2 id="quality-up-title" class="text-sm font-semibold text-ink">Load quality results</h2>
    <form class="space-y-3" @submit.prevent="submit">
      <div>
        <label :for="inputId" class="block text-sm font-medium text-ink">
          Quality results (.csv or .xlsx)
        </label>
        <input
          :id="inputId"
          ref="picker"
          type="file"
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          class="mt-1 block w-full max-w-md text-sm text-ink file:mr-3 file:rounded-lg file:border file:border-line file:bg-surface file:px-3 file:py-2 file:text-sm"
          @change="choose"
        />
        <p class="mt-1 text-xs text-ink-muted">
          Columns: <code>login</code>, <code>date</code>, <code>score</code> (0 to 100) and, if you
          have them, <code>kind</code> (call or ticket), <code>ref</code>, <code>csat</code> (1 to
          5) and <code>coaching_due</code>. Logins must already be linked to a person. Any other
          column (comments, names) is ignored and never stored. This layout is a stand-in until the
          quality tool is named.
        </p>
      </div>
      <AppButton type="submit" :loading="importQuality.isPending.value" :disabled="!file">
        {{ importQuality.isPending.value ? 'Importing…' : 'Import results' }}
      </AppButton>
    </form>

    <div aria-live="polite">
      <NoticeBox v-if="importQuality.isError.value" tone="danger" data-testid="quality-error">
        <p class="font-medium">Nothing was imported.</p>
        <p>{{ problemMessage(importQuality.error.value) }}</p>
      </NoticeBox>
      <div
        v-else-if="importQuality.data.value"
        class="space-y-2 text-sm"
        data-testid="quality-done"
      >
        <NoticeBox>
          {{ importQuality.data.value.rowsCreated }} added,
          {{ importQuality.data.value.rowsUpdated }} corrected,
          {{ importQuality.data.value.rowsUnchanged }} already held, of
          {{ importQuality.data.value.rowsRead }} rows.
          {{ importQuality.data.value.rowsRejected }} rejected,
          {{ importQuality.data.value.rowsUnmapped }} for logins not linked to a person.
        </NoticeBox>
        <NoticeBox v-if="importQuality.data.value.ignoredColumns.length > 0" data-testid="ignored">
          Not read or stored: {{ importQuality.data.value.ignoredColumns.join(', ') }}.
        </NoticeBox>
        <NoticeBox v-if="importQuality.data.value.unmappedLoginCount > 0" tone="warn">
          <p class="font-medium">
            Logins not linked to a person ({{ importQuality.data.value.unmappedLoginCount }}):
          </p>
          <p data-testid="unmapped">{{ importQuality.data.value.unmappedLogins.join(', ') }}</p>
          <p>Link them on the employee's record, then load the file again.</p>
        </NoticeBox>
        <NoticeBox v-if="importQuality.data.value.errors.length > 0" tone="warn">
          <p class="font-medium">Rows that were rejected:</p>
          <ul class="list-disc pl-5" data-testid="row-errors">
            <li v-for="e in importQuality.data.value.errors" :key="e.row">
              Line {{ e.row }}: {{ e.reason }}
            </li>
          </ul>
        </NoticeBox>
      </div>
    </div>
  </section>
</template>
