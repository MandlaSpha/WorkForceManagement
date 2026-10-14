<script setup lang="ts">
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useRosterStatus } from '../model/useRosterStatus'

const props = defineProps<{ queueId: number; weekStart: string; published: boolean }>()
const { publish, reopen } = useRosterStatus()

const action = () =>
  props.published
    ? reopen.mutate({ queueId: props.queueId, weekStart: props.weekStart })
    : publish.mutate({ queueId: props.queueId, weekStart: props.weekStart })
const pending = () => publish.isPending.value || reopen.isPending.value
const error = () => (publish.isError.value ? publish.error.value : reopen.error.value)
</script>

<template>
  <div class="inline-flex flex-col items-end gap-1">
    <AppButton :variant="published ? 'secondary' : 'primary'" :loading="pending()" @click="action">
      {{ published ? 'Return to draft' : 'Publish' }}
    </AppButton>
    <p
      v-if="publish.isError.value || reopen.isError.value"
      class="max-w-64 text-right text-xs text-danger"
      role="alert"
    >
      {{ problemMessage(error()) }}
    </p>
  </div>
</template>
