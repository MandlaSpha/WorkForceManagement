<script setup lang="ts">
import { formatCount, useImports } from '@/entities/call-data'
import { problemMessage } from '@/shared/api'
import { formatDate, formatDateTime } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const imports = useImports()
</script>

<template>
  <section aria-labelledby="import-history-title" class="space-y-3">
    <h2 id="import-history-title" class="text-base font-semibold text-ink">Previous imports</h2>

    <p v-if="imports.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="imports.isError.value" tone="danger">
      Could not load the import list. {{ problemMessage(imports.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(imports.data.value ?? []).length === 0"
      >Nothing has been imported yet.</NoticeBox
    >

    <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full min-w-[36rem] text-left text-sm">
        <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-4 py-2 font-medium">Imported</th>
            <th scope="col" class="px-3 py-2 font-medium">File</th>
            <th scope="col" class="px-3 py-2 font-medium">Calls from</th>
            <th scope="col" class="px-3 py-2 text-right font-medium">Added</th>
            <th scope="col" class="px-3 py-2 font-medium">Reconciles</th>
            <th scope="col" class="px-4 py-2 font-medium">By</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in imports.data.value" :key="item.id" class="border-b border-line">
            <td class="px-4 py-2 tabular-nums">{{ formatDateTime(item.createdAt) }}</td>
            <td class="px-3 py-2">{{ item.fileName }}</td>
            <td class="px-3 py-2">
              {{ formatDate(item.periodStart) }} – {{ formatDate(item.periodEnd) }}
            </td>
            <td class="px-3 py-2 text-right tabular-nums">{{ formatCount(item.rowsInserted) }}</td>
            <td
              class="px-3 py-2"
              :class="item.reconciles ? 'text-ink' : 'font-semibold text-danger'"
            >
              {{ item.reconciles ? 'Yes' : 'No' }}
            </td>
            <td class="px-4 py-2">{{ item.uploadedBy }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
