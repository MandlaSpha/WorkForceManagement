<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import {
  describe,
  isOpen,
  shiftLabel,
  STATUS_LABEL,
  STATUS_TONE,
  useBoard,
  useSwaps,
} from '@/entities/swap'
import type { Swap, SwapAnswer } from '@/entities/swap'
import { SwapActions } from '@/features/swap/answer'
import { OfferSwapForm } from '@/features/swap/offer'
import { TakeSwapPanel } from '@/features/swap/take'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import TabBar from '@/shared/ui/TabBar.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'swaps')
// Cosmetic: the API refuses approving for any other role.
const decides = computed(() => ['lead', 'planner', 'admin'].includes(session.user?.role ?? ''))

const all = useSwaps(null)
const board = useBoard()
const mine = computed(() => (all.data.value ?? []).filter((s) => s.asker || s.colleague))
// What still needs somebody comes first; finished swaps are history, a few at a time.
const active = computed(() => mine.value.filter((s) => isOpen(s.status)))
const finished = computed(() => mine.value.filter((s) => !isOpen(s.status)))
const HISTORY_SHOWN = 5
const showAllHistory = ref(false)
const history = computed(() =>
  showAllHistory.value ? finished.value : finished.value.slice(0, HISTORY_SHOWN),
)
const toApprove = computed(() =>
  (all.data.value ?? []).filter((s) => s.status === 'awaiting_approval'),
)
// Team requests nobody has taken yet: the lead or planner can see them coming, not act on them.
const stillOpen = computed(() =>
  (all.data.value ?? []).filter((s) => s.status === 'open' && !s.asker && !s.colleague),
)
const taking = ref<number | null>(null) // the board request whose "take" panel is open

// What the last answer did, kept on the page: the swap changes list as soon as it is answered,
// and its row goes with it.
const outcome = ref('')
const VERB: Record<SwapAnswer, string> = {
  approve: 'Approved',
  reject: 'Rejected',
  cancel: 'Withdrew',
}
function reported(what: SwapAnswer, swap: Swap): void {
  const done = what === 'approve' ? ' The two shifts have been exchanged on the roster.' : ''
  outcome.value = `${VERB[what]}: ${describe(swap)}.${done}`
}
function taken(message: string): void {
  outcome.value = message
  taking.value = null
}

const tab = ref('mine')
const TABS = computed(() => [
  { key: 'mine', label: 'My swaps' },
  { key: 'board', label: 'Open requests' },
  ...(decides.value ? [{ key: 'approvals', label: 'Approvals' }] : []),
])
</script>

<template>
  <PageHeader
    eyebrow="People"
    :title="screen?.label ?? 'Shift swaps'"
    :subtitle="screen?.subtitle"
  />

  <div class="space-y-4">
    <TabBar v-model="tab" :tabs="TABS" label="Shift swap sections" id-prefix="swaps" />
    <NoticeBox v-if="outcome" data-testid="swap-result" role="status">{{ outcome }}</NoticeBox>

    <div
      v-if="tab === 'mine'"
      id="swaps-panel-mine"
      role="tabpanel"
      aria-labelledby="swaps-tab-mine"
      class="space-y-6"
      aria-live="polite"
    >
      <section class="space-y-2" aria-labelledby="offer-title">
        <h2 id="offer-title" class="text-base font-semibold text-ink">Post a swap request</h2>
        <p class="text-sm text-ink-muted">
          Pick one of your shifts. Colleagues on the same queue whose own shifts would keep both of
          you within the rest, hours, leave and availability rules see it under Open requests,
          without your name. One of them takes it by offering a shift of theirs, then a lead
          approves.
        </p>
        <OfferSwapForm />
      </section>

      <p v-if="all.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="all.isError.value" tone="danger">
        Could not load your swaps. {{ problemMessage(all.error.value) }}
      </NoticeBox>
      <div v-else class="space-y-6">
        <section class="space-y-2" aria-labelledby="mine-title">
          <h2 id="mine-title" class="text-base font-semibold text-ink">Waiting</h2>
          <NoticeBox v-if="mine.length === 0">You have not posted or taken a swap.</NoticeBox>
          <NoticeBox v-else-if="active.length === 0" data-testid="none-waiting">
            Nothing is waiting on you or on anybody else.
          </NoticeBox>
          <ul v-else class="space-y-3" aria-label="My swaps">
            <li
              v-for="s in active"
              :key="s.id"
              class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4"
              :data-testid="`mine-${s.id}`"
            >
              <div>
                <p class="text-sm text-ink">{{ describe(s) }}</p>
                <span
                  class="mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  :class="STATUS_TONE[s.status]"
                >
                  {{ STATUS_LABEL[s.status] ?? s.status }}
                </span>
              </div>
              <SwapActions :swap="s" :decides="decides" @answered="reported" />
            </li>
          </ul>
        </section>

        <section v-if="finished.length > 0" class="space-y-2" aria-labelledby="history-title">
          <h2 id="history-title" class="text-base font-semibold text-ink">Earlier swaps</h2>
          <ul
            class="divide-y divide-line rounded-xl border border-line bg-surface"
            aria-label="Earlier swaps"
          >
            <li
              v-for="s in history"
              :key="s.id"
              class="flex flex-wrap items-center justify-between gap-2 px-4 py-2"
              :data-testid="`mine-${s.id}`"
            >
              <p class="text-sm text-ink-muted">{{ describe(s) }}</p>
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                :class="STATUS_TONE[s.status]"
              >
                {{ STATUS_LABEL[s.status] ?? s.status }}
              </span>
            </li>
          </ul>
          <button
            v-if="finished.length > HISTORY_SHOWN"
            type="button"
            class="text-sm font-medium text-brand-ink underline"
            data-testid="history-toggle"
            @click="showAllHistory = !showAllHistory"
          >
            {{ showAllHistory ? 'Show fewer' : `Show all ${finished.length} earlier swaps` }}
          </button>
        </section>
      </div>
    </div>

    <div
      v-else-if="tab === 'board'"
      id="swaps-panel-board"
      role="tabpanel"
      aria-labelledby="swaps-tab-board"
      class="space-y-3"
      aria-live="polite"
    >
      <p class="text-sm text-ink-muted">
        Shifts colleagues on your queues want to swap away, and that one of your own shifts could be
        traded for without breaking a rule. You are not told who posted them.
      </p>
      <p v-if="board.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="board.isError.value" tone="danger">
        Could not load the open requests. {{ problemMessage(board.error.value) }}
      </NoticeBox>
      <NoticeBox v-else-if="(board.data.value ?? []).length === 0" data-testid="board-empty">
        There are no open requests you could take.
      </NoticeBox>
      <ul v-else class="space-y-3" aria-label="Open swap requests">
        <li
          v-for="r in board.data.value"
          :key="r.id"
          class="rounded-xl border border-line bg-surface p-4"
          :data-testid="`board-${r.id}`"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="text-sm text-ink">
              A colleague on <span class="font-medium">{{ r.queue }}</span> wants to swap away
              <span class="font-medium">{{
                shiftLabel(r.day, r.shift, r.startTime, r.endTime)
              }}</span>
            </p>
            <button
              type="button"
              class="text-sm font-medium text-brand-ink underline"
              :aria-expanded="taking === r.id"
              :aria-label="`${taking === r.id ? 'Close' : 'Take'} the ${r.shift} request on ${r.day}`"
              @click="taking = taking === r.id ? null : r.id"
            >
              {{ taking === r.id ? 'Close' : 'Take it…' }}
            </button>
          </div>
          <TakeSwapPanel v-if="taking === r.id" :request="r" @taken="taken" />
        </li>
      </ul>
    </div>

    <div
      v-else
      id="swaps-panel-approvals"
      role="tabpanel"
      aria-labelledby="swaps-tab-approvals"
      class="space-y-3"
      aria-live="polite"
    >
      <p v-if="all.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="toApprove.length === 0" data-testid="nothing-to-approve">
        No swaps are waiting for approval.
      </NoticeBox>
      <ul v-else class="space-y-3" aria-label="Swaps waiting for approval">
        <li
          v-for="s in toApprove"
          :key="s.id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4"
          :data-testid="`approve-${s.id}`"
        >
          <p class="text-sm text-ink">
            {{ describe(s) }} <span class="text-ink-muted">({{ s.queue }})</span>
          </p>
          <p v-if="s.asker || s.colleague" class="text-xs text-ink-muted">
            Somebody else decides a swap you are in.
          </p>
          <SwapActions v-else :swap="s" :decides="decides" @answered="reported" />
        </li>
      </ul>

      <section v-if="stillOpen.length > 0" class="space-y-2" aria-labelledby="open-title">
        <h2 id="open-title" class="text-base font-semibold text-ink">Waiting for a colleague</h2>
        <p class="text-sm text-ink-muted">
          Posted by your team and not taken yet. They reach you for approval once a colleague takes
          them.
        </p>
        <ul class="space-y-2" aria-label="Open team requests">
          <li
            v-for="s in stillOpen"
            :key="s.id"
            class="rounded-xl border border-line bg-surface px-4 py-2 text-sm text-ink"
            :data-testid="`open-${s.id}`"
          >
            {{ describe(s) }} <span class="text-ink-muted">({{ s.queue }})</span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
