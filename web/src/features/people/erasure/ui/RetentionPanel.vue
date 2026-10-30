<script setup lang="ts">
import { problemMessage } from '@/shared/api'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useRetention } from '../model/erasure'

defineEmits<{ review: [employeeId: number] }>()
const retention = useRetention()
</script>

<template>
  <section class="space-y-2" aria-labelledby="retention-title">
    <h2 id="retention-title" class="text-base font-semibold text-ink">Past the retention period</h2>
    <NoticeBox v-if="retention.isError.value" tone="danger">
      {{ problemMessage(retention.error.value) }}
    </NoticeBox>
    <template v-else-if="retention.data.value">
      <p v-if="retention.data.value.employees.length === 0" class="text-sm text-ink-muted">
        Nobody is past the retention period.
      </p>
      <ul v-else class="space-y-1" aria-label="Leavers past retention">
        <li
          v-for="p in retention.data.value.employees"
          :key="p.employeeId"
          class="flex items-center gap-3 rounded-lg border border-line bg-surface px-3 py-1 text-sm"
        >
          <span class="font-medium tabular-nums">{{ p.employeeNumber }}</span>
          <span class="text-ink-muted">left {{ p.endDate }}</span>
          <button
            type="button"
            class="ml-auto text-sm font-medium text-brand-ink underline"
            :aria-label="`Review ${p.employeeNumber} for anonymising`"
            @click="$emit('review', p.employeeId)"
          >
            Review
          </button>
        </li>
      </ul>
    </template>
  </section>
</template>
