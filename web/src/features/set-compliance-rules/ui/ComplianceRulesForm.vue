<script setup lang="ts">
import { ref, watch } from 'vue'

import { useComplianceRules } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import { addDays, todayInJohannesburg } from '@/shared/lib/week'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveRules } from '../model/useSaveRules'

const rules = useComplianceRules()
const save = useSaveRules()

// Text first: a number input hands back a number once something is typed.
const effectiveFrom = ref(addDays(todayInJohannesburg(), 1))
const rest = ref('11')
const days = ref('6')
const cap = ref('')
const warnings = ref<string[]>([])

watch(
  () => rules.data.value?.inForce,
  (now) => {
    if (!now) return
    rest.value = String(now.minRestHours)
    days.value = String(now.maxConsecutiveDays)
    cap.value = now.maxWeeklyHours === null ? '' : String(now.maxWeeklyHours)
  },
  { immediate: true },
)

function submit(): void {
  const capText = String(cap.value).trim()
  save.mutate(
    {
      effectiveFrom: effectiveFrom.value,
      minRestHours: Number(String(rest.value).trim()),
      maxConsecutiveDays: Number(String(days.value).trim()),
      maxWeeklyHours: capText === '' ? null : Number(capText),
    },
    { onSuccess: (saved) => (warnings.value = saved.warnings) },
  )
}

function describe(r: {
  minRestHours: number
  maxConsecutiveDays: number
  maxWeeklyHours: number | null
}) {
  const limit = r.maxWeeklyHours === null ? 'no weekly cap' : `weekly cap ${r.maxWeeklyHours} h`
  return `${r.minRestHours} h rest, at most ${r.maxConsecutiveDays} days in a row, ${limit}`
}
</script>

<template>
  <form
    class="space-y-3 rounded-xl border border-line bg-surface p-4"
    aria-label="Compliance rules"
    @submit.prevent="submit"
  >
    <h3 class="text-sm font-semibold text-ink">Compliance rules</h3>
    <p class="text-sm text-ink-muted">
      Every roster, shift swap and auto-schedule is checked against these. A change starts on the
      day you choose and never rewrites a day already planned. Keeping to the law is the customer's
      responsibility: a rule can be tightened freely, and loosening it below the statutory minimum
      is allowed but is warned about.
    </p>

    <p v-if="rules.data.value" class="text-sm text-ink" data-testid="rules-in-force">
      <strong>In force today:</strong> {{ describe(rules.data.value.inForce) }}
      <template v-if="rules.data.value.inForce.effectiveFrom === null">
        (built-in defaults)</template
      >
    </p>
    <NoticeBox
      v-for="w in rules.data.value?.warnings ?? []"
      :key="w"
      tone="warn"
      data-testid="rules-warning"
    >
      {{ w }}
    </NoticeBox>

    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <TextField v-model="effectiveFrom" type="date" label="Starts on" />
      <TextField
        v-model="rest"
        type="number"
        label="Rest between shifts (hours)"
        :min="1"
        :max="24"
      />
      <TextField v-model="days" type="number" label="Most days in a row" :min="1" :max="14" />
      <TextField
        v-model="cap"
        type="number"
        label="Weekly hours cap (blank: contract hours only)"
        :min="1"
        :max="90"
      />
    </div>
    <AppButton type="submit" :loading="save.isPending.value" :disabled="rules.isPending.value">
      Save rules
    </AppButton>

    <NoticeBox v-if="save.isSuccess.value && warnings.length === 0" data-testid="rules-saved">
      Saved. These rules apply from {{ effectiveFrom }}.
    </NoticeBox>
    <NoticeBox v-for="w in warnings" :key="w" tone="warn" data-testid="rules-saved-warning">
      Saved, but: {{ w }}
    </NoticeBox>
    <NoticeBox v-if="save.isError.value" tone="danger" data-testid="rules-error">
      <p class="font-medium">The rules were not saved.</p>
      <p>{{ problemMessage(save.error.value) }}</p>
    </NoticeBox>

    <div v-if="(rules.data.value?.versions ?? []).length > 0">
      <h4 class="text-xs font-medium text-ink-muted">Versions</h4>
      <ul class="mt-1 space-y-1 text-sm text-ink" aria-label="Rule versions">
        <li v-for="v in rules.data.value?.versions" :key="v.effectiveFrom ?? 'default'">
          From {{ v.effectiveFrom }}: {{ describe(v) }}
        </li>
      </ul>
    </div>
  </form>
</template>
