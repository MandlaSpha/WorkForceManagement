<script setup lang="ts">
import type { Recommendation } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useApplyRecommendation } from '../model/useApplyRecommendation'

const props = defineProps<{ queueId: number; weekStart: string; recommendation: Recommendation }>()
const apply = useApplyRecommendation()

function submit(): void {
  const r = props.recommendation
  apply.mutate({
    queueId: props.queueId,
    weekStart: props.weekStart,
    employeeId: r.employeeId,
    day: r.day,
    templateId: r.templateId,
  })
}
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <AppButton :loading="apply.isPending.value" @click="submit">Apply</AppButton>
    <p v-if="apply.isError.value" class="max-w-64 text-right text-xs text-danger" role="alert">
      {{ problemMessage(apply.error.value) }}
    </p>
  </div>
</template>
