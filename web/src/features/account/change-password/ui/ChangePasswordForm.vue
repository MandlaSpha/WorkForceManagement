<script setup lang="ts">
import { computed, ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useChangePassword } from '../model/useChangePassword'

const emit = defineEmits<{ changed: [] }>()
const current = ref('')
const next = ref('')
const again = ref('')
const change = useChangePassword()

const mismatch = computed(() => again.value !== '' && again.value !== next.value)
const ready = computed(
  () => current.value !== '' && next.value !== '' && again.value === next.value,
)

function submit(): void {
  if (!ready.value) return
  change.mutate({ current: current.value, next: next.value }, { onSuccess: () => emit('changed') })
}
</script>

<template>
  <form class="max-w-md space-y-3" aria-label="Change your password" @submit.prevent="submit">
    <TextField
      v-model="current"
      type="password"
      label="Your current password"
      autocomplete="current-password"
    />
    <TextField v-model="next" type="password" label="New password" autocomplete="new-password" />
    <TextField
      v-model="again"
      type="password"
      label="New password again"
      autocomplete="new-password"
    />
    <p class="text-xs text-ink-muted">
      At least 12 characters, not a common password, not only digits.
    </p>
    <NoticeBox v-if="mismatch" tone="danger" data-testid="mismatch">
      The two new passwords are not the same.
    </NoticeBox>
    <AppButton type="submit" :loading="change.isPending.value" :disabled="!ready">
      Change password
    </AppButton>
    <NoticeBox v-if="change.isError.value" tone="danger" data-testid="change-error">
      <p class="font-medium">The password was not changed.</p>
      <p>{{ problemMessage(change.error.value) }}</p>
    </NoticeBox>
  </form>
</template>
