<script setup lang="ts">
import { problemMessage } from '@/shared/api'

import { useDeletePlan } from '../model/usePlanWrites'

const props = defineProps<{ planId: number; name: string }>()
const remove = useDeletePlan()
</script>

<template>
  <span>
    <button
      type="button"
      class="text-sm font-medium text-danger underline disabled:opacity-60"
      :aria-label="`Delete the plan ${name}`"
      :disabled="remove.isPending.value"
      @click="remove.mutate(props.planId)"
    >
      Delete plan
    </button>
    <span v-if="remove.isError.value" class="ml-2 text-xs text-danger" role="alert">
      {{ problemMessage(remove.error.value) }}
    </span>
  </span>
</template>
