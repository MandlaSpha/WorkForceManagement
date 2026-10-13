<script setup lang="ts">
import { ref, useId } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useImportReport } from '../model/useImportReport'
import ImportResult from './ImportResult.vue'

const inputId = useId()
const file = ref<File | null>(null)
const picker = ref<HTMLInputElement | null>(null)
const importReport = useImportReport()

function choose(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  importReport.reset()
}

function submit(): void {
  if (!file.value) return
  importReport.mutate(file.value, {
    onSuccess: () => {
      file.value = null
      if (picker.value) picker.value.value = ''
    },
  })
}
</script>

<template>
  <div class="space-y-6">
    <form class="space-y-3" @submit.prevent="submit">
      <div>
        <label :for="inputId" class="block text-sm font-medium text-ink">
          Call detail report (.xlsx)
        </label>
        <input
          :id="inputId"
          ref="picker"
          type="file"
          accept=".xlsx"
          class="mt-1 block w-full max-w-md text-sm text-ink file:mr-3 file:rounded-lg file:border file:border-line file:bg-surface file:px-3 file:py-2 file:text-sm"
          @change="choose"
        />
        <p class="mt-1 text-xs text-ink-muted">
          Phone numbers and agent names in the file are never stored.
        </p>
      </div>
      <AppButton type="submit" :loading="importReport.isPending.value" :disabled="!file">
        {{ importReport.isPending.value ? 'Importing…' : 'Import report' }}
      </AppButton>
    </form>

    <div aria-live="polite">
      <NoticeBox v-if="importReport.isError.value" tone="danger" data-testid="import-error">
        <p class="font-medium">Nothing was imported.</p>
        <p>{{ problemMessage(importReport.error.value) }}</p>
      </NoticeBox>
      <ImportResult v-else-if="importReport.data.value" :report="importReport.data.value" />
    </div>
  </div>
</template>
