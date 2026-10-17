<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useAnonymise, useErasurePreview } from '../model/erasure'

const props = defineProps<{ employeeId: number; employeeLabel: string }>()
const emit = defineEmits<{ done: []; cancel: [] }>()

const preview = useErasurePreview()
const anonymise = useAnonymise()
const typed = ref('')

const REMOVES: Record<string, string> = {
  agentLogins: 'ACD logins',
  availabilityWindows: 'availability windows',
  notifications: 'notifications',
  overtimeReasons: 'overtime reasons (free text)',
  payRecords: 'pay records',
  signInLinks: 'sign-in links',
}
const KEEPS: Record<string, string> = {
  shifts: 'shifts',
  leaveRequests: 'leave requests',
  overtimeRequests: 'overtime requests',
  standbyShifts: 'standby shifts',
}
const matches = computed(
  () =>
    preview.data.value !== undefined && typed.value.trim() === preview.data.value.employeeNumber,
)

onMounted(() => preview.mutate(props.employeeId))

function confirm(): void {
  anonymise.mutate(
    { employeeId: props.employeeId, employeeNumber: typed.value },
    { onSuccess: () => emit('done') },
  )
}
</script>

<template>
  <section
    class="space-y-3 rounded-xl border border-danger bg-surface p-4"
    role="group"
    aria-labelledby="anonymise-title"
  >
    <h2 id="anonymise-title" class="text-base font-semibold text-ink">
      Anonymise {{ employeeLabel }}
    </h2>
    <p v-if="preview.isPending.value" class="text-sm text-ink-muted">Checking…</p>
    <NoticeBox v-else-if="preview.isError.value" tone="danger">
      {{ problemMessage(preview.error.value) }}
    </NoticeBox>
    <template v-else-if="preview.data.value">
      <p class="text-sm text-ink">
        This cannot be undone. The name, employee number and sign-in are replaced, and the following
        are deleted:
      </p>
      <ul class="list-disc pl-6 text-sm text-ink" aria-label="Will be removed">
        <li v-for="(label, key) in REMOVES" :key="key">
          {{ preview.data.value.removes[key] ?? 0 }} {{ label }}
        </li>
      </ul>
      <p class="text-sm text-ink-muted">
        Kept without a name, so history and totals stay right:
        <template v-for="(label, key) in KEEPS" :key="key">
          {{ preview.data.value.keeps[key] ?? 0 }} {{ label }};
        </template>
      </p>
      <TextField v-model="typed" label="Type the employee number to confirm" autocomplete="off" />
      <NoticeBox v-if="anonymise.isError.value" tone="danger">
        {{ problemMessage(anonymise.error.value) }}
      </NoticeBox>
    </template>
    <div class="flex gap-2">
      <AppButton
        v-if="preview.data.value"
        :disabled="!matches"
        :loading="anonymise.isPending.value"
        @click="confirm"
      >
        Anonymise permanently
      </AppButton>
      <AppButton variant="secondary" @click="emit('cancel')">Cancel</AppButton>
    </div>
  </section>
</template>
