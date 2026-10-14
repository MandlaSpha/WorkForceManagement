<script setup lang="ts">
import { ref } from 'vue'

import { rejectReason } from '@/entities/service-desk'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useImportWorkItems } from '../model/useImportWorkItems'

const file = ref<File | null>(null)
const upload = useImportWorkItems()

function choose(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function submit(): void {
  if (file.value) upload.mutate(file.value)
}
</script>

<template>
  <section class="space-y-3" aria-labelledby="work-import-title">
    <h2 id="work-import-title" class="text-base font-semibold text-ink">Bring in work items</h2>
    <p class="text-sm text-ink-muted">
      A CSV exported from the ticketing tool, with the columns <code>ref</code>, <code>pool</code>,
      <code>opened</code> and, if you have them, <code>priority</code>, <code>due</code>,
      <code>effort_minutes</code> and <code>closed</code>. Items already known are updated, so the
      same export can be brought in again as tickets are closed. Any other column (names, emails,
      descriptions) is ignored and never stored.
    </p>
    <form class="space-y-3" aria-label="Import work items" @submit.prevent="submit">
      <div>
        <label for="work-file" class="block text-xs font-medium text-ink-muted">
          Work items (.csv)
        </label>
        <input
          id="work-file"
          type="file"
          accept=".csv,text/csv"
          class="mt-1 block text-sm text-ink"
          @change="choose"
        />
      </div>
      <AppButton type="submit" :loading="upload.isPending.value" :disabled="file === null">
        Import work items
      </AppButton>
    </form>

    <NoticeBox v-if="upload.isError.value" tone="danger" data-testid="work-import-error">
      <p class="font-medium">Nothing was imported.</p>
      <p>{{ problemMessage(upload.error.value) }}</p>
    </NoticeBox>

    <div v-if="upload.data.value" class="space-y-2" data-testid="work-import-result">
      <p class="text-sm text-ink">
        <strong>{{ upload.data.value.created }}</strong> added,
        <strong>{{ upload.data.value.updated }}</strong> updated,
        <strong>{{ upload.data.value.unchanged }}</strong> already up to date.
      </p>
      <NoticeBox v-if="Object.keys(upload.data.value.rejected).length > 0" tone="warn">
        <p class="font-medium">Some rows were not kept:</p>
        <ul class="list-disc pl-5">
          <li v-for="(count, reason) in upload.data.value.rejected" :key="reason">
            {{ count }} with {{ rejectReason(reason) }}
          </li>
        </ul>
      </NoticeBox>
      <NoticeBox v-if="upload.data.value.ignoredColumns.length > 0" data-testid="ignored-columns">
        Not read or stored: {{ upload.data.value.ignoredColumns.join(', ') }}.
      </NoticeBox>
    </div>
  </section>
</template>
