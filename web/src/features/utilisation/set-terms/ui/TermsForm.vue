<script setup lang="ts">
import { computed, ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveTerms } from '../model/useSaveTerms'

const props = defineProps<{ contractId: number; contractName: string; targetPct: number | null }>()

const save = useSaveTerms()
const target = ref(props.targetPct === null ? '' : String(props.targetPct))
const revenue = ref('')
const saved = ref(false)

const targetError = computed(() => {
  const n = Number(target.value)
  return target.value === '' || !(n > 0 && n <= 100) ? 'A target is above 0 and at most 100.' : ''
})

function submit() {
  saved.value = false
  if (targetError.value) return
  // Revenue is optional; leaving it empty clears it. The figure is never echoed back.
  save.mutate(
    {
      contractId: props.contractId,
      terms: {
        utilisationTargetPct: Number(target.value),
        monthlyRevenueRands: revenue.value === '' ? null : Number(revenue.value),
      },
    },
    { onSuccess: () => (saved.value = true) },
  )
}
</script>

<template>
  <form
    class="flex flex-wrap items-end gap-3"
    :aria-label="`Terms of ${contractName}`"
    @submit.prevent="submit"
  >
    <TextField
      v-model="target"
      label="Utilisation target (%)"
      type="number"
      :step="0.5"
      :min="1"
      :max="100"
      :error="targetError"
    />
    <TextField v-model="revenue" label="Monthly revenue (rands, optional)" type="number" :min="0" />
    <AppButton type="submit" :loading="save.isPending.value">Save terms</AppButton>
    <p v-if="saved" class="text-sm text-ink" role="status" data-testid="terms-saved">
      Saved. The revenue is kept but not shown again.
    </p>
    <NoticeBox v-if="save.isError.value" tone="danger" data-testid="terms-error">
      Nothing was saved. {{ problemMessage(save.error.value) }}
    </NoticeBox>
  </form>
</template>
