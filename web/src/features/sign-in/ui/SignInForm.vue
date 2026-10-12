<script setup lang="ts">
import { ref } from 'vue'

import { useSessionStore, type SessionUser } from '@/entities/session'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { signInErrorMessage } from '../model/messages'

const emit = defineEmits<{ signedIn: [user: SessionUser] }>()

const session = useSessionStore()
const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

/** Used by the dev-only demo panel; also keeps the form the single place that signs in. */
function fill(demoUsername: string, demoPassword: string): void {
  username.value = demoUsername
  password.value = demoPassword
}
defineExpose({ fill })

async function submit(): Promise<void> {
  error.value = ''
  submitting.value = true
  try {
    emit('signedIn', await session.signIn(username.value.trim(), password.value))
  } catch (e) {
    error.value = signInErrorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <form class="space-y-4" novalidate @submit.prevent="submit">
    <div>
      <h2 class="text-base font-semibold text-ink">Sign in</h2>
      <p class="text-xs text-ink-muted">Welcome back — sign in to continue.</p>
    </div>

    <NoticeBox v-if="session.expired" tone="warn">
      You were signed out after a period of inactivity. Please sign in again.
    </NoticeBox>

    <TextField v-model="username" label="Username" autocomplete="username" />
    <TextField
      v-model="password"
      label="Password"
      type="password"
      autocomplete="current-password"
    />

    <NoticeBox v-if="error" tone="danger">{{ error }}</NoticeBox>

    <AppButton
      type="submit"
      class="w-full"
      :loading="submitting"
      :disabled="!username || !password"
    >
      {{ submitting ? 'Signing in…' : 'Sign in' }}
    </AppButton>
  </form>
</template>
