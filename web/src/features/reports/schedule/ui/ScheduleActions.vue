<script setup lang="ts">
import { Pause, Play, Trash2 } from 'lucide-vue-next'
import { ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import Dialog from '@/shared/ui/Dialog.vue'

import { useChangeSchedule, useDeleteSchedule } from '../model/useSchedules'

const props = defineProps<{ scheduleId: number; what: string; paused: boolean }>()
const change = useChangeSchedule()
const remove = useDeleteSchedule()
const confirming = ref(false)

function confirmDelete(): void {
  remove.mutate(props.scheduleId, { onSuccess: () => (confirming.value = false) })
}

const ICON_BUTTON =
  'press inline-flex size-10 items-center justify-center rounded-xl text-ink-muted hover:bg-surface-muted hover:text-ink disabled:opacity-60'
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <div class="flex gap-1">
      <button
        type="button"
        :class="ICON_BUTTON"
        :aria-label="`${paused ? 'Resume' : 'Pause'} ${what}`"
        :title="paused ? 'Resume' : 'Pause'"
        :disabled="change.isPending.value"
        @click="change.mutate({ id: props.scheduleId, body: { paused: !paused } })"
      >
        <Play v-if="paused" :size="18" aria-hidden="true" />
        <Pause v-else :size="18" aria-hidden="true" />
      </button>
      <button
        type="button"
        :class="[ICON_BUTTON, 'hover:text-danger']"
        :aria-label="`Delete ${what}`"
        title="Delete"
        @click="confirming = true"
      >
        <Trash2 :size="18" aria-hidden="true" />
      </button>
    </div>
    <span v-if="change.isError.value" class="text-xs text-danger" role="alert">
      {{ problemMessage(change.error.value) }}
    </span>

    <Dialog v-model:open="confirming" size="sm" title="Delete this schedule?" :subtitle="what">
      <p class="text-sm text-ink-muted">
        Nothing more will be emailed from it. Reports already sent are not recalled.
      </p>
      <p v-if="remove.isError.value" class="mt-3 text-sm text-danger" role="alert">
        {{ problemMessage(remove.error.value) }}
      </p>
      <template #footer>
        <AppButton variant="ghost" @click="confirming = false">Keep it</AppButton>
        <AppButton :loading="remove.isPending.value" @click="confirmDelete">
          Delete schedule
        </AppButton>
      </template>
    </Dialog>
  </div>
</template>
