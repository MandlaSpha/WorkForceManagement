import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { addWeeks, formatWeekRange, todayInJohannesburg, weekStartOf } from '@/shared/lib/week'

export interface Option {
  value: string
  label: string
}

/**
 * The global site / queue / week the whole app is looking at (the top-bar pickers).
 * Sites and queues arrive from the API in Phase 1 (org module); until then the lists are
 * honestly empty and the pickers say so instead of showing invented choices.
 */
export const useContextStore = defineStore('context', () => {
  const sites = ref<Option[]>([])
  const queues = ref<Option[]>([])
  const siteId = ref('')
  const queueId = ref('')
  const weekStart = ref(weekStartOf(todayInJohannesburg()))

  const weekLabel = computed(() => formatWeekRange(weekStart.value))

  function previousWeek(): void {
    weekStart.value = addWeeks(weekStart.value, -1)
  }
  function nextWeek(): void {
    weekStart.value = addWeeks(weekStart.value, 1)
  }
  function setSites(next: Option[]): void {
    sites.value = next
    if (!next.some((s) => s.value === siteId.value)) siteId.value = next[0]?.value ?? ''
  }
  function setQueues(next: Option[]): void {
    queues.value = next
    if (!next.some((q) => q.value === queueId.value)) queueId.value = next[0]?.value ?? ''
  }

  return {
    sites,
    queues,
    siteId,
    queueId,
    weekStart,
    weekLabel,
    previousWeek,
    nextWeek,
    setSites,
    setQueues,
  }
})
