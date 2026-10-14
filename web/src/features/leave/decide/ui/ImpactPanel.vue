<script setup lang="ts">
import { useImpact } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import { formatMinutes } from '@/shared/lib/duration'

const props = defineProps<{ requestId: number }>()
const impact = useImpact(props.requestId, true)
</script>

<template>
  <div class="text-sm" data-testid="impact">
    <p v-if="impact.isPending.value" class="text-ink-muted">Working out the effect on coverage…</p>
    <p v-else-if="impact.isError.value" class="text-danger">
      Could not work out the effect. {{ problemMessage(impact.error.value) }}
    </p>
    <template v-else-if="impact.data.value">
      <p v-if="impact.data.value.shifts === 0" class="text-ink">
        No shifts on those days, so nothing changes in the roster.
      </p>
      <template v-else>
        <p class="text-ink">
          Takes {{ impact.data.value.shifts }}
          {{ impact.data.value.shifts === 1 ? 'shift' : 'shifts' }}
          ({{ formatMinutes(impact.data.value.hours * 60) }}) off the roster.
        </p>
        <p
          class="font-medium"
          :class="impact.data.value.newlyUnder > 0 ? 'text-danger' : 'text-ink'"
        >
          {{ impact.data.value.newlyUnder }} half-hours that are covered now would be short.
        </p>
        <p v-if="impact.data.value.alreadyUnder > 0" class="text-ink-muted">
          {{ impact.data.value.alreadyUnder }} half-hours that are already short would be shorter.
        </p>
        <p v-if="impact.data.value.unknown > 0" class="text-ink-muted">
          {{ impact.data.value.unknown }} half-hours have no known requirement, so nothing is said
          about them.
        </p>
      </template>
    </template>
  </div>
</template>
