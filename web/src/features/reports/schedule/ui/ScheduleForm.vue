<script setup lang="ts">
import { FileBarChart, Gauge, Presentation } from 'lucide-vue-next'
import { computed, ref, useId } from 'vue'

import type { QueueInfo } from '@/entities/call-data'
import { FREQUENCY_LABEL, REPORT_BLURB, REPORT_LABEL, WEEKDAYS } from '@/entities/report-schedule'
import { problemMessage } from '@/shared/api'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import SettingsCard from '@/shared/ui/SettingsCard.vue'
import SettingsFooter from '@/shared/ui/SettingsFooter.vue'
import SettingsRow from '@/shared/ui/SettingsRow.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useCreateSchedule } from '../model/useSchedules'

const props = defineProps<{
  queues: ReadonlyArray<QueueInfo>
  /** Reports this person may schedule (a lead has no scorecard). */
  reports: ReadonlyArray<string>
  domains: ReadonlyArray<string>
}>()

const ICON = { scorecard: Gauge, peaks: FileBarChart, board: Presentation } as const

const uid = useId()
const create = useCreateSchedule()
const report = ref(props.reports[0] ?? 'scorecard')
const queueId = ref('')
const recipients = ref('')
const frequency = ref('daily')
const hour = ref('7')
const weekday = ref('0')
const dayOfMonth = ref('1')

const queueOptions = computed(() =>
  props.queues.map((q) => ({ value: String(q.id), label: q.name })),
)
const frequencyOptions = Object.entries(FREQUENCY_LABEL).map(([value, label]) => ({ value, label }))
const weekdayOptions = WEEKDAYS.map((label, n) => ({ value: String(n), label }))
const hourOptions = Array.from({ length: 24 }, (_, n) => ({
  value: String(n),
  label: `${String(n).padStart(2, '0')}:00`,
}))
const dirty = computed(() => recipients.value.trim() !== '')

function discard(): void {
  recipients.value = ''
}

function submit(): void {
  create.mutate(
    {
      report: report.value,
      queueId: report.value === 'peaks' && queueId.value !== '' ? Number(queueId.value) : null,
      recipients: recipients.value
        .split(/[\n,;]+/)
        .map((a) => a.trim())
        .filter(Boolean),
      frequency: frequency.value,
      hour: Number(hour.value),
      weekday: Number(weekday.value),
      dayOfMonth: Number(dayOfMonth.value),
    },
    { onSuccess: () => (recipients.value = '') },
  )
}
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
    <section
      class="rounded-3xl bg-surface p-5 shadow-[var(--shadow-card)] sm:p-6"
      aria-labelledby="report-type-title"
    >
      <h2 id="report-type-title" class="text-lg font-semibold tracking-tight text-ink">
        Report type
      </h2>
      <p class="mt-1 text-sm text-ink-muted">What the emailed report holds.</p>
      <div class="mt-4 space-y-2" role="radiogroup" aria-labelledby="report-type-title">
        <label
          v-for="r in reports"
          :key="r"
          class="press flex cursor-pointer items-start gap-3 rounded-2xl border p-3 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand"
          :class="
            report === r ? 'border-brand bg-brand-soft' : 'border-line hover:bg-surface-muted'
          "
          :data-testid="`report-option-${r}`"
        >
          <input
            v-model="report"
            type="radio"
            class="sr-only"
            name="report-type"
            :value="r"
            :aria-describedby="`${uid}-${r}`"
          />
          <span
            class="grid size-9 shrink-0 place-items-center rounded-xl bg-surface text-brand-ink"
            aria-hidden="true"
          >
            <component :is="ICON[r as keyof typeof ICON] ?? FileBarChart" :size="18" />
          </span>
          <span class="min-w-0">
            <span class="block text-sm font-semibold text-ink">{{ REPORT_LABEL[r] ?? r }}</span>
            <span :id="`${uid}-${r}`" class="mt-0.5 block text-xs text-ink-muted">
              {{ REPORT_BLURB[r] ?? '' }}
            </span>
          </span>
        </label>
      </div>
    </section>

    <form aria-label="Schedule a report" @submit.prevent="submit">
      <SettingsCard
        title="When and to whom"
        :description="`${REPORT_LABEL[report] ?? report}. The report holds only what you may see.`"
      >
        <NoticeBox v-if="domains.length === 0" tone="warn" data-testid="no-domains" class="my-4">
          No email domain has been allowed yet, so reports cannot be sent. Ask your administrator to
          allow one.
        </NoticeBox>
        <SettingsRow
          label="Send to"
          :helper="
            domains.length > 0
              ? `One address per line, on ${domains.join(', ')}.`
              : 'One address per line, on an allowed domain.'
          "
        >
          <label class="block">
            <span class="sr-only">Send to (one address per line)</span>
            <textarea
              v-model="recipients"
              rows="3"
              class="block w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink"
            />
          </label>
        </SettingsRow>
        <SettingsRow
          v-if="report === 'peaks'"
          label="Queue"
          helper="Peaks and troughs is worked out for one queue."
        >
          <SelectField
            v-model="queueId"
            label="Queue"
            hide-label
            :options="queueOptions"
            empty-text="No queues yet"
          />
        </SettingsRow>
        <SettingsRow label="How often" helper="Sent on this rhythm until you pause or delete it.">
          <SelectField
            v-model="frequency"
            label="How often"
            hide-label
            :options="frequencyOptions"
          />
        </SettingsRow>
        <SettingsRow v-if="frequency === 'weekly'" label="On" helper="The day of the week.">
          <SelectField v-model="weekday" label="On" hide-label :options="weekdayOptions" />
        </SettingsRow>
        <SettingsRow
          v-if="frequency === 'monthly'"
          label="Day of the month"
          helper="1 to 28, so every month has the day."
        >
          <TextField
            v-model="dayOfMonth"
            type="number"
            label="Day of the month (1 to 28)"
            hide-label
            :min="1"
            :max="28"
          />
        </SettingsRow>
        <SettingsRow label="At" helper="South African time.">
          <SelectField
            v-model="hour"
            label="At (South African time)"
            hide-label
            :options="hourOptions"
          />
        </SettingsRow>
        <template #footer>
          <SettingsFooter
            :dirty="dirty"
            clean-text="Add an address to schedule"
            submit-label="Schedule report"
            :loading="create.isPending.value"
            :disabled="recipients.trim() === '' || (report === 'peaks' && queueId === '')"
            @discard="discard"
          />
          <p
            v-if="create.isSuccess.value"
            class="mt-2 text-sm text-ink"
            data-testid="schedule-result"
          >
            Scheduled.
          </p>
          <p
            v-if="create.isError.value"
            class="mt-2 text-sm text-danger"
            role="alert"
            data-testid="schedule-error"
          >
            {{ problemMessage(create.error.value) }}
          </p>
        </template>
      </SettingsCard>
    </form>
  </div>
</template>
