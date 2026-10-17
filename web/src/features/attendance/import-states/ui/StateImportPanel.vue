<script setup lang="ts">
import { ref, useId } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useImportStates } from '../model/useImportStates'

const inputId = useId()
const file = ref<File | null>(null)
const picker = ref<HTMLInputElement | null>(null)
const importStates = useImportStates()

function choose(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  importStates.reset()
}

function submit(): void {
  if (!file.value) return
  importStates.mutate(file.value, {
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
    aria-labelledby="up-title"
  >
    <h2 id="up-title" class="text-sm font-semibold text-ink">Load agent states</h2>
    <form class="space-y-3" @submit.prevent="submit">
      <div>
        <label :for="inputId" class="block text-sm font-medium text-ink">
          Agent-state file (.csv)
        </label>
        <input
          :id="inputId"
          ref="picker"
          type="file"
          accept=".csv,text/csv"
          class="mt-1 block w-full max-w-md text-sm text-ink file:mr-3 file:rounded-lg file:border file:border-line file:bg-surface file:px-3 file:py-2 file:text-sm"
          @change="choose"
        />
        <p class="mt-1 text-xs text-ink-muted">
          Columns: login, state, from, to (local date-times). Logins must already be linked to a
          person. This layout is a stand-in until the ACD vendor confirms the real feed.
        </p>
      </div>
      <AppButton type="submit" :loading="importStates.isPending.value" :disabled="!file">
        {{ importStates.isPending.value ? 'Importing…' : 'Import states' }}
      </AppButton>
    </form>

    <div aria-live="polite">
      <NoticeBox v-if="importStates.isError.value" tone="danger" data-testid="states-error">
        <p class="font-medium">Nothing was imported.</p>
        <p>{{ problemMessage(importStates.error.value) }}</p>
      </NoticeBox>
      <div v-else-if="importStates.data.value" class="space-y-2 text-sm" data-testid="states-done">
        <NoticeBox>
          {{ importStates.data.value.rowsInserted }} of {{ importStates.data.value.rowsRead }} rows
          stored. {{ importStates.data.value.rowsDuplicate }} already held,
          {{ importStates.data.value.rowsRejected }} rejected,
          {{ importStates.data.value.rowsUnmapped }} for logins not linked to a person.
        </NoticeBox>
        <NoticeBox v-if="importStates.data.value.unmappedLoginCount > 0" tone="warn">
          <p class="font-medium">
            Logins not linked to a person ({{ importStates.data.value.unmappedLoginCount }}):
          </p>
          <p data-testid="unmapped">{{ importStates.data.value.unmappedLogins.join(', ') }}</p>
          <p>Link them on the employee's record, then load the file again.</p>
        </NoticeBox>
        <NoticeBox v-if="importStates.data.value.errors.length > 0" tone="warn">
          <p class="font-medium">Rows that were rejected:</p>
          <ul class="list-disc pl-5" data-testid="row-errors">
            <li v-for="e in importStates.data.value.errors" :key="e.row">
              Line {{ e.row }}: {{ e.reason }}
            </li>
          </ul>
        </NoticeBox>
      </div>
    </div>
  </section>
</template>
