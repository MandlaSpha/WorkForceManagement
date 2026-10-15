<script setup lang="ts">
import { computed } from 'vue'

import {
  KIND_LABEL,
  KIND_TONE,
  useAvailability,
  WEEKDAYS,
  windowLabel,
} from '@/entities/availability'
import { DeclareWindowForm, RemoveWindowButton } from '@/features/people/availability'
import { ApiProblem, problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'my-availability')
const windows = useAvailability()
const noRecord = computed(
  () =>
    windows.error.value instanceof ApiProblem &&
    windows.error.value.code === 'availability.no_employee_record',
)
const byDay = computed(() =>
  WEEKDAYS.map((name, index) => ({
    name,
    items: (windows.data.value ?? []).filter((w) => w.weekday === index),
  })).filter((d) => d.items.length > 0),
)
</script>

<template>
  <PageHeader
    eyebrow="My work"
    :title="screen?.label ?? 'My availability'"
    :subtitle="screen?.subtitle"
  />

  <div class="space-y-6" aria-live="polite">
    <NoticeBox v-if="noRecord" data-testid="no-record">
      You are not on the employee list yet, so there is nothing to declare. A planner adds you.
    </NoticeBox>
    <template v-else>
      <NoticeBox data-testid="how-it-works">
        <p>
          <strong>Cannot work</strong> times are respected: the roster will not put you on a shift
          that covers them. <strong>Would rather work</strong> times are wishes the planner can see.
        </p>
        <p class="mt-1">
          They repeat every week. If you declare nothing, the planner knows nothing: it does not
          mean you are free.
        </p>
      </NoticeBox>

      <section class="space-y-2" aria-labelledby="declare-title">
        <h2 id="declare-title" class="text-base font-semibold text-ink">Add a time</h2>
        <DeclareWindowForm />
      </section>

      <section class="space-y-2" aria-labelledby="declared-title">
        <h2 id="declared-title" class="text-base font-semibold text-ink">What you have declared</h2>
        <p v-if="windows.isPending.value" class="text-sm text-ink-muted">Loading…</p>
        <NoticeBox v-else-if="windows.isError.value" tone="danger">
          Could not load your availability. {{ problemMessage(windows.error.value) }}
        </NoticeBox>
        <NoticeBox v-else-if="byDay.length === 0" data-testid="nothing-declared">
          You have not declared anything.
        </NoticeBox>
        <ul v-else class="space-y-3" aria-label="Declared availability">
          <li
            v-for="d in byDay"
            :key="d.name"
            class="rounded-xl border border-line bg-surface p-4"
            :data-testid="`day-${d.name}`"
          >
            <p class="text-sm font-semibold text-ink">{{ d.name }}</p>
            <ul class="mt-2 space-y-2">
              <li v-for="w in d.items" :key="w.id" class="flex items-center justify-between gap-3">
                <span class="text-sm text-ink">
                  <span class="tabular-nums">{{ windowLabel(w.startTime, w.endTime) }}</span>
                  <span
                    class="ml-2 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                    :class="KIND_TONE[w.kind]"
                  >
                    {{ KIND_LABEL[w.kind] ?? w.kind }}
                  </span>
                </span>
                <RemoveWindowButton
                  :window-id="w.id"
                  :label="`${d.name} ${windowLabel(w.startTime, w.endTime)}`"
                />
              </li>
            </ul>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
