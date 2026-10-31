<script setup lang="ts">
import type { Flex } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useApplyFlex } from '../model/useApplyFlex'

const props = defineProps<{ queueId: number; weekStart: string; flex: Flex }>()
const apply = useApplyFlex()

function submit(): void {
  apply.mutate({
    queueId: props.queueId,
    weekStart: props.weekStart,
    employeeId: props.flex.employeeId,
    day: props.flex.day,
  })
}
</script>

<template>
  <div class="flex flex-col items-end gap-1">
    <AppButton
      :loading="apply.isPending.value"
      :aria-label="`Borrow ${flex.employee} from ${flex.fromQueue}`"
      @click="submit"
    >
      Borrow
    </AppButton>
    <p v-if="apply.isError.value" class="max-w-64 text-right text-xs text-danger" role="alert">
      {{ problemMessage(apply.error.value) }}
    </p>
  </div>
</template>
