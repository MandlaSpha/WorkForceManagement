<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { reportKeys, saveAllowedDomains } from '@/entities/report-schedule'
import { problemMessage } from '@/shared/api'
import { refreshQueries } from '@/shared/lib/refresh'
import SettingsCard from '@/shared/ui/SettingsCard.vue'
import SettingsFooter from '@/shared/ui/SettingsFooter.vue'
import SettingsRow from '@/shared/ui/SettingsRow.vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

const props = defineProps<{ domains: ReadonlyArray<string> }>()
const text = ref(props.domains.join('\n'))
watch(
  () => props.domains,
  (d) => (text.value = d.join('\n')),
)
const dirty = computed(() => text.value !== props.domains.join('\n'))
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
  <form aria-label="Allowed email domains" @submit.prevent="submit">
    <SettingsCard
      title="Allowed email domains"
      description="Reports can only be emailed to addresses on these domains."
    >
      <SettingsRow label="Domains" helper="One per line, such as example.co.za.">
        <label class="block">
          <span class="sr-only">Email domains reports may be sent to (one per line)</span>
          <textarea
            v-model="text"
            rows="3"
            class="block w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink"
          />
        </label>
      </SettingsRow>
      <template #footer>
        <SettingsFooter
          :dirty="dirty"
          clean-text="All changes saved"
          submit-label="Save domains"
          :loading="save.isPending.value"
          @discard="text = props.domains.join('\n')"
        />
        <p v-if="save.isSuccess.value" class="mt-2 text-sm text-ink" data-testid="domains-saved">
          Saved.
        </p>
        <p v-if="save.isError.value" class="mt-2 text-sm text-danger" role="alert">
          {{ problemMessage(save.error.value) }}
        </p>
      </template>
    </SettingsCard>
  </form>
</template>
