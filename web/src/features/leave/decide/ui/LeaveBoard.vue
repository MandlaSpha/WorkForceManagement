<script setup lang="ts">
import { CalendarDays } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import {
  canMoveLeave,
  groupLeave,
  isMovableLeave,
  formatDays,
  rangeLabel,
  useRequests,
} from '@/entities/leave'
import type { Decision, LeaveRequest } from '@/entities/leave'
import { problemMessage } from '@/shared/api'
import KanbanBoard from '@/shared/ui/KanbanBoard.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import ReasonDialog from '@/shared/ui/ReasonDialog.vue'

import { useDecideLeave } from '../model/useDecideLeave'
import LeaveCoverageChip from './LeaveCoverageChip.vue'

const props = defineProps<{ decides: boolean }>()
const emit = defineEmits<{ decided: [who: string, decision: Decision, reason?: string] }>()

const all = useRequests(null)
const decide = useDecideLeave()
const board = ref<{ focusCard: (id: number) => Promise<void> } | null>(null)

// The card moves the moment it is dropped; if the API refuses, it goes back.
const optimistic = ref<Record<number, string>>({})
const announcement = ref('')
const failure = ref('')
const rejecting = ref<LeaveRequest | null>(null)
const asking = computed({
  get: () => rejecting.value !== null,
  set: (v: boolean) => {
    if (!v) rejecting.value = null
  },
})

const requests = computed(() =>
  (all.data.value ?? []).map((r) => {
    const status = optimistic.value[r.id]
    return status ? { ...r, status } : r
  }),
)
const columns = computed(() => groupLeave(requests.value, props.decides))

const label = (r: LeaveRequest) => `${r.leaveType} for ${r.employee}`

function move(item: LeaveRequest, to: string): void {
  if (to === 'rejected') {
    rejecting.value = item
    return
  }
  run(item, 'approve')
}

function run(item: LeaveRequest, what: 'approve' | 'reject', reason?: string): void {
  failure.value = ''
  const verb = what === 'approve' ? 'Approved' : 'Rejected'
  optimistic.value = {
    ...optimistic.value,
    [item.id]: what === 'approve' ? 'approved' : 'rejected',
  }
  announcement.value = `${verb}: ${label(item)}.`
  void board.value?.focusCard(item.id)
  decide.mutate(
    { requestId: item.id, what },
    {
      onSuccess: (decision) => emit('decided', item.employee, decision, reason),
      onError: (error) => {
        failure.value = `Could not move ${label(item)}: ${problemMessage(error)} It is back where it was.`
        announcement.value = failure.value
      },
      onSettled: () => {
        const rest = { ...optimistic.value }
        delete rest[item.id]
        optimistic.value = rest
        void board.value?.focusCard(item.id)
      },
    },
  )
}

function rejected(reason: string): void {
  const item = rejecting.value
  if (item) run(item, 'reject', reason)
}
</script>

<template>
  <div class="space-y-3" data-testid="leave-board">
    <NoticeBox v-if="all.isError.value" tone="danger">
      Could not load the requests. {{ problemMessage(all.error.value) }}
    </NoticeBox>
    <NoticeBox v-if="failure" tone="danger" role="alert" data-testid="board-failure">
      {{ failure }}
    </NoticeBox>
    <KanbanBoard
      ref="board"
      :columns="columns"
      label="Leave requests by stage"
      :loading="all.isPending.value"
      :item-label="label"
      :movable="(r: LeaveRequest) => isMovableLeave(r, decides)"
      :can-move="(r: LeaveRequest, to: string) => canMoveLeave(r, to, decides)"
      :announcement="announcement"
      @move="move"
    >
      <template #card="{ item }">
        <div class="flex items-start gap-3">
          <span
            class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand-ink"
            aria-hidden="true"
          >
            <CalendarDays :size="16" />
          </span>
          <div class="min-w-0 flex-1 space-y-1">
            <p class="text-sm font-semibold text-ink">{{ item.employee }}</p>
            <p class="text-xs text-ink-muted">
              {{ rangeLabel(item.startDate, item.endDate) }}, {{ formatDays(item.days) }}
            </p>
            <div class="flex flex-wrap gap-1.5 pt-1">
              <span
                class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-ink"
                >{{ item.leaveType }}</span
              >
              <LeaveCoverageChip v-if="item.status === 'pending'" :request-id="item.id" />
            </div>
          </div>
        </div>
      </template>
    </KanbanBoard>
    <ReasonDialog
      v-model:open="asking"
      title="Reject this leave request"
      subtitle="Say why. The reason is shown in the confirmation on this page."
      confirm-label="Reject leave"
      @confirm="rejected"
    />
  </div>
</template>
