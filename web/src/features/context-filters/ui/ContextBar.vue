<script setup lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

import SelectField from '@/shared/ui/SelectField.vue'

import { useContextStore } from '../model/store'
import { useSyncQueues } from '../model/useSyncQueues'

withDefaults(defineProps<{ showScope?: boolean }>(), { showScope: true })

const context = useContextStore()
useSyncQueues()
</script>

<template>
  <div class="flex flex-wrap items-end gap-3">
    <div v-if="showScope" class="w-44">
      <SelectField
        v-model="context.siteId"
        label="Site"
        :options="context.sites"
        empty-text="No sites yet"
      />
    </div>
    <div v-if="showScope" class="w-40">
      <SelectField
        v-model="context.queueId"
        label="Queue"
        :options="context.queues"
        empty-text="No queues yet"
      />
    </div>
    <div
      class="flex items-center rounded-lg border border-line bg-surface"
      role="group"
      aria-label="Week"
    >
      <button
        type="button"
        class="inline-flex size-9 items-center justify-center text-ink-muted hover:text-ink"
        aria-label="Previous week"
        @click="context.previousWeek()"
      >
        <ChevronLeft :size="16" aria-hidden="true" />
      </button>
      <span class="min-w-32 px-1 text-center text-sm text-ink" aria-live="polite">
        {{ context.weekLabel }}
      </span>
      <button
        type="button"
        class="inline-flex size-9 items-center justify-center text-ink-muted hover:text-ink"
        aria-label="Next week"
        @click="context.nextWeek()"
      >
        <ChevronRight :size="16" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
