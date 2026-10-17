<script setup lang="ts">
import { ref, watch } from 'vue'

import { reportKeys, saveAllowedDomains } from '@/entities/report-schedule'
import { problemMessage } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'
import AppButton from '@/shared/ui/AppButton.vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

const props = defineProps<{ domains: ReadonlyArray<string> }>()
const text = ref(props.domains.join('\n'))
watch(
  () => props.domains,
  (d) => (text.value = d.join('\n')),
)
const queryClient = useQueryClient()
const save = useMutation({
  mutationFn: (domains: string[]) => saveAllowedDomains(domains),
  onSuccess: () => refreshQueries(queryClient, reportKeys.all),
})

function submit(): void {
  save.mutate(
    text.value
      .split(/[\n,;]+/)
      .map((d) => d.trim())
      .filter(Boolean),
  )
}
</script>

<template>
  <form
    class="space-y-2 rounded-xl border border-line bg-surface p-4"
    aria-label="Allowed email domains"
    @submit.prevent="submit"
  >
    <label class="block text-xs font-medium text-ink-muted">
      Email domains reports may be sent to (one per line, such as example.co.za)
      <textarea
        v-model="text"
        rows="3"
        class="mt-1 block w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink"
      />
    </label>
    <div class="flex items-center gap-3">
      <AppButton type="submit" :loading="save.isPending.value">Save domains</AppButton>
      <span v-if="save.isSuccess.value" class="text-sm text-ink" data-testid="domains-saved"
        >Saved.</span
      >
    </div>
    <p v-if="save.isError.value" class="text-sm text-danger" role="alert">
      {{ problemMessage(save.error.value) }}
    </p>
  </form>
</template>
