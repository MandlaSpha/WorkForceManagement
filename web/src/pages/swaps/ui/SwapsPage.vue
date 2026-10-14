<script setup lang="ts">
import { computed, ref } from 'vue'

import { useSessionStore } from '@/entities/session'
import { describe, isOpen, STATUS_LABEL, STATUS_TONE, useSwaps } from '@/entities/swap'
import type { Swap, SwapAnswer } from '@/entities/swap'
import { SwapActions } from '@/features/swap/answer'
import { OfferSwapForm } from '@/features/swap/offer'
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
const mine = computed(() => (all.data.value ?? []).filter((s) => s.asker || s.colleague))
const forMe = computed(() =>
  mine.value.filter((s) => s.colleague && s.status === 'awaiting_colleague'),
)
const others = computed(() => mine.value.filter((s) => !forMe.value.includes(s)))
const toApprove = computed(() =>
  (all.data.value ?? []).filter((s) => s.status === 'awaiting_approval'),
)

// What the last answer did, kept on the page: the swap changes list as soon as it is answered,
// and its row goes with it.
const outcome = ref('')
const VERB: Record<SwapAnswer, string> = {
  accept: 'Accepted',
  decline: 'Declined',
  approve: 'Approved',
  reject: 'Rejected',
  cancel: 'Withdrew',
}
function reported(what: SwapAnswer, swap: Swap): void {
  const done = what === 'approve' ? ' The two shifts have been exchanged on the roster.' : ''
  outcome.value = `${VERB[what]}: ${describe(swap)}.${done}`
}

const tab = ref('mine')
const TABS = computed(() => [
  { key: 'mine', label: 'My swaps' },
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
        <h2 id="offer-title" class="text-base font-semibold text-ink">Offer a swap</h2>
        <p class="text-sm text-ink-muted">
          Pick one of your shifts and a colleague's shift on the same queue. Only swaps that keep
          both of you within the rest, hours and leave rules are listed. Your colleague accepts,
          then a lead approves.
        </p>
        <OfferSwapForm />
      </section>

      <p v-if="all.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="all.isError.value" tone="danger">
        Could not load your swaps. {{ problemMessage(all.error.value) }}
      </NoticeBox>
      <template v-else>
        <section v-if="forMe.length > 0" class="space-y-2" aria-labelledby="forme-title">
          <h2 id="forme-title" class="text-base font-semibold text-ink">Waiting for your answer</h2>
          <ul class="space-y-3" aria-label="Swaps waiting for your answer">
            <li
              v-for="s in forMe"
              :key="s.id"
              class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4"
              :data-testid="`for-me-${s.id}`"
            >
              <p class="text-sm text-ink">{{ describe(s) }}</p>
              <SwapActions :swap="s" :decides="decides" @answered="reported" />
            </li>
          </ul>
        </section>

        <section class="space-y-2" aria-labelledby="mine-title">
          <h2 id="mine-title" class="text-base font-semibold text-ink">My swaps</h2>
          <NoticeBox v-if="others.length === 0">
            You have not offered or been offered a swap.
          </NoticeBox>
          <ul v-else class="space-y-3" aria-label="My swaps">
            <li
              v-for="s in others"
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
              <SwapActions
                v-if="isOpen(s.status)"
                :swap="s"
                :decides="decides"
                @answered="reported"
              />
            </li>
          </ul>
        </section>
      </template>
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
    </div>
  </div>
</template>
