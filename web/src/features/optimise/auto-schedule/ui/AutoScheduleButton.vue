<script setup lang="ts">
import { computed } from 'vue'

import { problemMessage } from '@/shared/api'
import { formatDayLabel } from '@/shared/lib/datetime'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useAutoSchedule } from '../model/useAutoSchedule'

const props = defineProps<{ queueId: number; weekStart: string }>()
const { preview, apply } = useAutoSchedule()

const body = () => ({ queueId: props.queueId, weekStart: props.weekStart })
const proposal = computed(() => preview.data.value)
const result = computed(() => apply.data.value)
const skipped = computed(() =>
  Object.values(result.value?.skipped ?? {}).reduce((a, b) => a + b, 0),
)

function dismiss(): void {
  preview.reset()
  apply.reset()
}
</script>

<template>
  <div class="space-y-3">
    <AppButton
      variant="secondary"
      :loading="preview.isPending.value"
      @click="preview.mutate(body())"
    >
      Auto-schedule
    </AppButton>

    <NoticeBox v-if="preview.isError.value" tone="danger" data-testid="auto-error">
      <p class="font-medium">Auto-schedule could not run.</p>
      <p>{{ problemMessage(preview.error.value) }}</p>
    </NoticeBox>
    <NoticeBox v-if="apply.isError.value" tone="danger" data-testid="auto-error">
      <p class="font-medium">The roster was not filled.</p>
      <p>{{ problemMessage(apply.error.value) }}</p>
    </NoticeBox>

    <section
      v-if="proposal && !result"
      class="space-y-3 rounded-xl border border-line bg-surface p-4"
      aria-label="Auto-schedule proposal"
      data-testid="auto-proposal"
    >
      <p v-if="proposal.status === 'none'" class="text-sm text-ink">
        No roster could be found that keeps every rule. Nothing was changed.
      </p>
      <template v-else>
        <p class="text-sm text-ink" data-testid="auto-summary">
          <strong>{{ proposal.placements.length }}</strong>
          {{ proposal.placements.length === 1 ? 'shift' : 'shifts' }} would be added
          <template v-if="proposal.kept > 0"> to the {{ proposal.kept }} already rostered</template
          >. Half-hours short: <strong>{{ proposal.shortBefore }}</strong> now,
          <strong>{{ proposal.shortAfter }}</strong> after.
          <template v-if="proposal.overAfter > 0">
            {{ proposal.overAfter }} would have one person too many.
          </template>
        </p>
        <p
          v-if="proposal.placements.length === 0 && proposal.shortAfter > 0"
          class="text-sm text-ink-muted"
          data-testid="auto-nothing-fits"
        >
          Nobody free can fill the gap without breaking a roster rule, or no shift in the library
          would fix more than it would overstaff. Add a shorter shift or free someone up.
        </p>
        <p v-if="proposal.status === 'feasible'" class="text-xs text-ink-muted">
          The search stopped on its time limit, so this is a good roster but not proven the best.
        </p>
        <ul
          v-if="proposal.placements.length > 0"
          class="max-h-48 space-y-1 overflow-y-auto text-sm text-ink"
          aria-label="Shifts to be added"
        >
          <li v-for="p in proposal.placements" :key="`${p.employeeId}-${p.day}`">
            {{ p.employee }}: {{ formatDayLabel(p.day) }}, {{ p.shift }}
          </li>
        </ul>
        <p class="text-xs text-ink-muted">
          Existing shifts are never changed, and every shift is checked against the roster rules
          again when applied.
        </p>
        <div class="flex gap-2">
          <AppButton
            v-if="proposal.placements.length > 0"
            :loading="apply.isPending.value"
            @click="apply.mutate(body())"
          >
            Apply these shifts
          </AppButton>
          <AppButton variant="ghost" @click="dismiss">Dismiss</AppButton>
        </div>
      </template>
    </section>

    <NoticeBox v-if="result" data-testid="auto-result">
      Added {{ result.placed }} {{ result.placed === 1 ? 'shift' : 'shifts' }}.
      <template v-if="skipped > 0">
        {{ skipped }} could not be added because the roster rules refused them.
      </template>
      Half-hours short: {{ result.shortBefore }} before, {{ result.shortAfter }} now.
      <AppButton variant="ghost" @click="dismiss">Close</AppButton>
    </NoticeBox>
  </div>
</template>
