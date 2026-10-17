<script setup lang="ts">
import { useAuditChain } from '@/entities/audit-log'
import { problemMessage } from '@/shared/api'
import { formatDateTime } from '@/shared/lib/datetime'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const chain = useAuditChain()
</script>

<template>
  <section aria-label="Hash chain" data-testid="chain-status">
    <p v-if="chain.isPending.value" class="text-sm text-ink-muted">Checking the hash chain…</p>
    <NoticeBox v-else-if="chain.isError.value" tone="danger">
      Could not check the hash chain. {{ problemMessage(chain.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="chain.data.value?.intact">
      Hash chain intact: all {{ chain.data.value.events }} events verified, none removed, inserted
      or changed. Checked {{ formatDateTime(chain.data.value.checkedAt) }}.
    </NoticeBox>
    <NoticeBox v-else-if="chain.data.value" tone="danger">
      <p class="font-medium">
        The hash chain is broken: {{ chain.data.value.problemCount }} problem(s) found. Treat the
        trail as tampered with and tell your security contact.
      </p>
      <ul class="mt-1 list-disc pl-5 text-xs">
        <li v-for="p in chain.data.value.problems" :key="`${p.seq}-${p.eventId}`">
          Event {{ p.eventId ?? '?' }} (sequence {{ p.seq ?? '?' }}): {{ p.problem }}
        </li>
      </ul>
    </NoticeBox>
  </section>
</template>
