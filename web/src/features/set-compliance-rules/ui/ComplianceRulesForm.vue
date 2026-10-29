<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useComplianceRules } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import { addDays, todayInJohannesburg } from '@/shared/lib/week'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SettingsCard from '@/shared/ui/SettingsCard.vue'
import SettingsFooter from '@/shared/ui/SettingsFooter.vue'
import SettingsRow from '@/shared/ui/SettingsRow.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useSaveRules } from '../model/useSaveRules'

const rules = useComplianceRules()
const save = useSaveRules()

// Text first: a number input hands back a number once something is typed.
const effectiveFrom = ref(addDays(todayInJohannesburg(), 1))
const rest = ref('11')
const days = ref('6')
const cap = ref('')
const overtime = ref('1.5')
const sunday = ref('2')
const holiday = ref('2')
const warnings = ref<string[]>([])

function load(): void {
  const now = rules.data.value?.inForce
  if (!now) return
  rest.value = String(now.minRestHours)
  days.value = String(now.maxConsecutiveDays)
  cap.value = now.maxWeeklyHours === null ? '' : String(now.maxWeeklyHours)
  overtime.value = String(now.overtimeMultiplier)
  sunday.value = String(now.sundayMultiplier)
  holiday.value = String(now.holidayMultiplier)
}
watch(() => rules.data.value?.inForce, load, { immediate: true })

/** Edits to the values (the start date is always a choice, so it does not count). */
const dirty = computed(() => {
  const now = rules.data.value?.inForce
  if (!now) return false
  return (
    rest.value !== String(now.minRestHours) ||
    days.value !== String(now.maxConsecutiveDays) ||
    String(cap.value) !== (now.maxWeeklyHours === null ? '' : String(now.maxWeeklyHours)) ||
    overtime.value !== String(now.overtimeMultiplier) ||
    sunday.value !== String(now.sundayMultiplier) ||
    holiday.value !== String(now.holidayMultiplier)
  )
})

function discard(): void {
  load()
  warnings.value = []
  save.reset()
}

function submit(): void {
  const capText = String(cap.value).trim()
  save.mutate(
    {
      effectiveFrom: effectiveFrom.value,
      minRestHours: Number(String(rest.value).trim()),
      maxConsecutiveDays: Number(String(days.value).trim()),
      maxWeeklyHours: capText === '' ? null : Number(capText),
      overtimeMultiplier: Number(String(overtime.value).trim()),
      sundayMultiplier: Number(String(sunday.value).trim()),
      holidayMultiplier: Number(String(holiday.value).trim()),
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
  <form aria-label="Compliance rules" @submit.prevent="submit">
    <SettingsCard
      title="Compliance rules"
      description="Every roster, shift swap and auto-schedule is checked against these. A change starts on the day you choose and never rewrites a day already planned. Keeping to the law is the customer's responsibility: a rule can be tightened freely, and loosening it below the statutory minimum is allowed but is warned about."
    >
      <div
        v-if="rules.isPending.value"
        class="space-y-2 py-4"
        aria-busy="true"
        aria-label="Loading"
      >
        <div class="skeleton h-10" />
        <div class="skeleton h-10" />
      </div>
      <NoticeBox v-else-if="rules.isError.value" tone="danger" class="my-4">
        Could not load the rules. {{ problemMessage(rules.error.value) }}
      </NoticeBox>
      <div v-if="rules.data.value" class="space-y-1 py-4 text-sm text-ink">
        <p data-testid="rules-in-force">
          <strong>In force today:</strong> {{ describe(rules.data.value.inForce) }}
          <template v-if="rules.data.value.inForce.effectiveFrom === null">
            (built-in defaults)</template
          >
        </p>
        <p data-testid="rules-pay">
          <strong>Overtime pays:</strong> {{ rules.data.value.inForce.overtimeMultiplier }}x on a
          weekday, {{ rules.data.value.inForce.sundayMultiplier }}x on a Sunday,
          {{ rules.data.value.inForce.holidayMultiplier }}x on a public holiday.
        </p>
      </div>
      <div v-if="(rules.data.value?.warnings ?? []).length > 0" class="space-y-2 py-4">
        <NoticeBox
          v-for="w in rules.data.value?.warnings"
          :key="w"
          tone="warn"
          data-testid="rules-warning"
        >
          {{ w }}
        </NoticeBox>
      </div>

      <SettingsRow label="Starts on" helper="The day the new rules begin; earlier days are kept.">
        <TextField v-model="effectiveFrom" type="date" label="Starts on" hide-label />
      </SettingsRow>
      <SettingsRow
        label="Rest between shifts"
        helper="Hours off between the end of one shift and the next."
      >
        <TextField
          v-model="rest"
          type="number"
          label="Rest between shifts (hours)"
          hide-label
          :min="1"
          :max="24"
        />
      </SettingsRow>
      <SettingsRow label="Most days in a row" helper="The longest run of working days.">
        <TextField
          v-model="days"
          type="number"
          label="Most days in a row"
          hide-label
          :min="1"
          :max="14"
        />
      </SettingsRow>
      <SettingsRow label="Weekly hours cap" helper="Leave blank to use contract hours only.">
        <TextField
          v-model="cap"
          type="number"
          label="Weekly hours cap (blank: contract hours only)"
          hide-label
          :min="1"
          :max="90"
        />
      </SettingsRow>
      <SettingsRow label="Overtime pay" helper="Times the hourly rate on a weekday.">
        <TextField
          v-model="overtime"
          type="number"
          label="Overtime pay (times the hourly rate)"
          hide-label
          :min="1"
          :max="4"
          :step="0.05"
        />
      </SettingsRow>
      <SettingsRow label="Sunday pay" helper="Times the hourly rate on a Sunday.">
        <TextField
          v-model="sunday"
          type="number"
          label="Sunday pay (times the hourly rate)"
          hide-label
          :min="1"
          :max="4"
          :step="0.05"
        />
      </SettingsRow>
      <SettingsRow label="Public holiday pay" helper="Times the hourly rate on a public holiday.">
        <TextField
          v-model="holiday"
          type="number"
          label="Public holiday pay (times the hourly rate)"
          hide-label
          :min="1"
          :max="4"
          :step="0.05"
        />
      </SettingsRow>

      <div v-if="(rules.data.value?.versions ?? []).length > 0" class="py-4">
        <h3 class="text-sm font-semibold text-ink">Versions</h3>
        <ul class="mt-1 space-y-1 text-sm text-ink-muted" aria-label="Rule versions">
          <li v-for="v in rules.data.value?.versions" :key="v.effectiveFrom ?? 'default'">
            From {{ v.effectiveFrom }}: {{ describe(v) }}
          </li>
        </ul>
      </div>

      <template #footer>
        <SettingsFooter
          :dirty="dirty"
          clean-text="All changes saved"
          submit-label="Save rules"
          :loading="save.isPending.value"
          :disabled="rules.isPending.value"
          @discard="discard"
        />
        <div class="mt-3 space-y-2">
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
        </div>
      </template>
    </SettingsCard>
  </form>
</template>
