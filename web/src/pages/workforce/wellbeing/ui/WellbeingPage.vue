<script setup lang="ts">
import { flagText, useWellbeing } from '@/entities/workforce/wellbeing'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'wellbeing')
const wellbeing = useWellbeing()
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Wellbeing'" :subtitle="screen?.subtitle" />

  <div class="space-y-4">
    <NoticeBox data-testid="how-it-works">
      These are prompts for a conversation, not a score or a verdict. They come from rostered days,
      approved overtime and unplanned leave. They are shown to the lead of the team and to planners,
      and to nobody else.
    </NoticeBox>

    <section aria-live="polite">
      <p v-if="wellbeing.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="wellbeing.isError.value" tone="danger" data-testid="wellbeing-error">
        Could not load the prompts. {{ problemMessage(wellbeing.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="wellbeing.data.value?.people.length === 0" data-testid="nobody">
        Nobody has a prompt as of {{ wellbeing.data.value.asOf }}.
      </NoticeBox>
      <ul v-else class="space-y-3" aria-label="People with a prompt">
        <li
          v-for="p in wellbeing.data.value?.people"
          :key="p.employeeId"
          class="rounded-xl border border-line bg-surface p-4"
          :data-testid="`person-${p.empNo}`"
        >
          <p class="text-sm font-semibold text-ink">
            {{ p.employee }} <span class="font-normal text-ink-muted">({{ p.empNo }})</span>
          </p>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-sm text-ink">
            <li v-for="f in p.flags" :key="f.code">{{ flagText(f.code, f.value) }}</li>
          </ul>
        </li>
      </ul>
    </section>
  </div>
</template>
