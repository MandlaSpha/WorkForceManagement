<script setup lang="ts">
import { ArrowLeftRight } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import {
  canMoveSwap,
  groupSwaps,
  isMovableSwap,
  shiftLabel,
  STATUS_LABEL,
  STATUS_TONE,
  describe,
  useSwaps,
} from '@/entities/swap'
import type { Swap } from '@/entities/swap'
import { problemMessage } from '@/shared/api'
import KanbanBoard from '@/shared/ui/KanbanBoard.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import ReasonDialog from '@/shared/ui/ReasonDialog.vue'

import { useAnswerSwap } from '../model/useAnswerSwap'

const props = defineProps<{ decides: boolean }>()
const emit = defineEmits<{ answered: [message: string] }>()

const all = useSwaps(null)
const answer = useAnswerSwap()
const board = ref<{ focusCard: (id: number) => Promise<void> } | null>(null)

// The card moves the moment it is dropped; if the API refuses, it goes back.
const optimistic = ref<Record<number, string>>({})
const announcement = ref('')
const failure = ref('')
const declining = ref<Swap | null>(null)
const asking = computed({
  get: () => declining.value !== null,
  set: (v: boolean) => {
    if (!v) declining.value = null
  },
})

const swaps = computed(() =>
  (all.data.value ?? []).map((s) => {
    const status = optimistic.value[s.id]
    return status ? { ...s, status } : s
  }),
)
const columns = computed(() => groupSwaps(swaps.value, props.decides))

const label = (s: Swap) => `the ${s.fromShift} swap on ${shiftLabel(s.fromDay, s.fromShift)}`

function move(item: Swap, to: string): void {
  if (to === 'declined') {
    declining.value = item
    return
  }
  run(item, 'approve')
}

function run(item: Swap, what: 'approve' | 'reject', reason?: string): void {
  failure.value = ''
  const verb = what === 'approve' ? 'Approved' : 'Declined'
  optimistic.value = {
    ...optimistic.value,
    [item.id]: what === 'approve' ? 'approved' : 'rejected',
  }
  announcement.value = `${verb}: ${label(item)}.`
  void board.value?.focusCard(item.id)
  answer.mutate(
    { swapId: item.id, what },
    {
      onSuccess: () => {
        const extra = what === 'approve' ? ' The two shifts have been exchanged on the roster.' : ''
        const why = reason ? ` Reason: ${reason}.` : ''
        emit('answered', `${verb}: ${describe(item)}.${extra}${why}`)
      },
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

function declined(reason: string): void {
  const item = declining.value
  if (item) run(item, 'reject', reason)
}
</script>

<template>
  <div class="space-y-3" data-testid="swap-board">
    <NoticeBox v-if="all.isError.value" tone="danger">
      Could not load the swaps. {{ problemMessage(all.error.value) }}
    </NoticeBox>
    <NoticeBox v-if="failure" tone="danger" role="alert" data-testid="board-failure">
      {{ failure }}
    </NoticeBox>
    <KanbanBoard
      ref="board"
      :columns="columns"
      label="Shift swaps by stage"
      :loading="all.isPending.value"
      :item-label="label"
      :movable="(s: Swap) => isMovableSwap(s, decides)"
      :can-move="(s: Swap, to: string) => canMoveSwap(s, to, decides)"
      :announcement="announcement"
      @move="move"
    >
      <template #card="{ item }">
        <div class="flex items-start gap-3">
          <span
            class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand-ink"
            aria-hidden="true"
          >
            <ArrowLeftRight :size="16" />
          </span>
          <div class="min-w-0 flex-1 space-y-1">
            <p class="text-sm font-semibold text-ink">
              {{ shiftLabel(item.fromDay, item.fromShift) }}
              <template v-if="item.toDay && item.toShift">
                for {{ shiftLabel(item.toDay, item.toShift) }}
              </template>
            </p>
            <!-- A lead, planner or admin sees the names they see today. An agent sees the
                 sentence the list gives them, which hides what must be hidden. -->
            <p v-if="decides" class="text-xs text-ink-muted" data-testid="swap-people">
              {{ item.fromEmployee }}
              <template v-if="item.toEmployee"> and {{ item.toEmployee }}</template>
              <template v-else> (not taken yet)</template>
            </p>
            <p v-else class="text-xs text-ink-muted">{{ describe(item) }}</p>
            <div class="flex flex-wrap gap-1.5 pt-1">
              <span
                class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-ink"
                >{{ item.queue }}</span
              >
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                :class="STATUS_TONE[item.status]"
                >{{ STATUS_LABEL[item.status] ?? item.status }}</span
              >
            </div>
          </div>
        </div>
      </template>
    </KanbanBoard>
    <p v-if="!decides" class="text-xs text-ink-muted">
      These are the swaps you are in. A lead or planner decides them.
    </p>
    <ReasonDialog
      v-model:open="asking"
      title="Decline this swap"
      subtitle="Say why. The reason is shown in the confirmation on this page."
      confirm-label="Decline swap"
      @confirm="declined"
    />
  </div>
</template>
