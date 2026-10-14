<script setup lang="ts">
import { ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { useSetPoolMinutes } from '../model/useSetPoolMinutes'

const props = defineProps<{ poolId: number; pool: string; minutes: number }>()
const value = ref(String(props.minutes))
const save = useSetPoolMinutes()

function submit(): void {
  save.mutate({ poolId: props.poolId, minutes: Number(value.value) })
}
</script>

<template>
  <form
    class="flex items-center gap-1"
    :aria-label="`Productive minutes for ${pool}`"
    @submit.prevent="submit"
  >
    <input
      v-model="value"
      type="number"
      min="30"
      max="600"
      class="w-20 rounded-md border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums text-ink"
      :aria-label="`Productive minutes a day for ${pool}`"
    />
    <AppButton type="submit" variant="ghost" :loading="save.isPending.value">Save</AppButton>
    <span
      v-if="save.isError.value"
      class="text-xs text-danger"
      role="alert"
      :data-testid="`minutes-error-${poolId}`"
    >
      {{ problemMessage(save.error.value) }}
    </span>
  </form>
</template>
