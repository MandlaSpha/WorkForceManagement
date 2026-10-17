<script setup lang="ts">
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useChangeSchedule, useDeleteSchedule } from '../model/useSchedules'

const props = defineProps<{ scheduleId: number; what: string; paused: boolean }>()
const change = useChangeSchedule()
const remove = useDeleteSchedule()
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <div class="flex gap-2">
      <AppButton
        variant="secondary"
        :aria-label="`${paused ? 'Resume' : 'Pause'} ${what}`"
        :loading="change.isPending.value"
        @click="change.mutate({ id: props.scheduleId, body: { paused: !paused } })"
      >
        {{ paused ? 'Resume' : 'Pause' }}
      </AppButton>
      <button
        type="button"
        class="text-xs font-medium text-danger underline disabled:opacity-60"
        :aria-label="`Delete ${what}`"
        :disabled="remove.isPending.value"
        @click="remove.mutate(props.scheduleId)"
      >
        Delete
      </button>
    </div>
    <span
      v-if="change.isError.value || remove.isError.value"
      class="text-xs text-danger"
      role="alert"
    >
      {{ problemMessage(change.error.value ?? remove.error.value) }}
    </span>
  </div>
</template>
