<script setup lang="ts">
import { problemMessage } from '@/shared/api'

import { useRemoveWindow } from '../model/useAvailabilityEdits'

const props = defineProps<{ windowId: number; label: string }>()
const remove = useRemoveWindow()
</script>

<template>
  <span class="inline-flex flex-col items-end">
    <button
      type="button"
      class="text-xs font-medium text-danger underline disabled:opacity-60"
      :aria-label="`Remove ${label}`"
      :disabled="remove.isPending.value"
      @click="remove.mutate(props.windowId)"
    >
      Remove
    </button>
    <span v-if="remove.isError.value" class="text-xs text-danger" role="alert">
      {{ problemMessage(remove.error.value) }}
    </span>
  </span>
</template>
