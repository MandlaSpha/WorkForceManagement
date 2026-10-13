<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { useSessionStore, type SessionUser } from '@/entities/session'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { LOCAL_ONLY, type SignInProvider } from '../model/providers'
import { signInErrorMessage, ssoErrorMessage } from '../model/messages'
import SsoButtons from './SsoButtons.vue'

const props = withDefaults(
  defineProps<{
    providers?: readonly SignInProvider[]
    /** `?error=` from an SSO round trip. */
    ssoError?: unknown
    /** Where to go after signing in; handed to SSO providers. */
    next?: string
  }>(),
  { providers: () => LOCAL_ONLY, ssoError: undefined, next: undefined },
)
const emit = defineEmits<{ signedIn: [user: SessionUser] }>()

const session = useSessionStore()
const username = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

// Username-and-password providers (local, LDAP). Restricted local accounts are emergency access
// only, so they stay out of the normal choice.
const credentialProviders = computed(() =>
  props.providers.filter((p) => p.flow === 'credentials' && !p.restricted),
)
const emergency = computed(() =>
  props.providers.find((p) => p.flow === 'credentials' && p.restricted),
)
const ssoProviders = computed(() => props.providers.filter((p) => p.flow === 'redirect'))

const chosen = ref('')
// The dropdown must always show a real choice. An unset value matches no option and the browser
// then renders an empty box, even though the first provider would be used.
watch(
  credentialProviders,
  (list) => {
    if (!list.some((p) => p.id === chosen.value)) chosen.value = list[0]?.id ?? ''
  },
  { immediate: true },
)
const emergencyOpen = ref(false)
const activeProvider = computed(() =>
  emergencyOpen.value && emergency.value
    ? emergency.value.id
    : chosen.value || credentialProviders.value[0]?.id || 'local',
)
const showForm = computed(() => credentialProviders.value.length > 0 || emergencyOpen.value)
const bannerError = computed(() => error.value || ssoErrorMessage(props.ssoError))

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
    emit(
      'signedIn',
      await session.signIn(username.value.trim(), password.value, activeProvider.value),
    )
  } catch (e) {
    error.value = signInErrorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-base font-semibold text-ink">Sign in</h2>
      <p class="text-xs text-ink-muted">Welcome back — sign in to continue.</p>
    </div>

    <NoticeBox v-if="session.expired" tone="warn">
      You were signed out after a period of inactivity. Please sign in again.
    </NoticeBox>
    <NoticeBox v-if="bannerError" tone="danger">{{ bannerError }}</NoticeBox>

    <SsoButtons :providers="ssoProviders" :next="next" />

    <p
      v-if="ssoProviders.length && showForm"
      class="text-center text-[11px] uppercase tracking-wide text-ink-muted"
    >
      or
    </p>

    <form v-if="showForm" class="space-y-4" novalidate @submit.prevent="submit">
      <SelectField
        v-if="credentialProviders.length > 1 && !emergencyOpen"
        v-model="chosen"
        label="Sign in with"
        :options="credentialProviders.map((p) => ({ value: p.id, label: p.label }))"
      />
      <NoticeBox v-if="emergencyOpen">
        Emergency access for administrators. Everyone else signs in with their organisation account.
      </NoticeBox>

      <TextField v-model="username" label="Username" autocomplete="username" />
      <TextField
        v-model="password"
        label="Password"
        type="password"
        autocomplete="current-password"
      />

      <AppButton
        type="submit"
        class="w-full"
        :loading="submitting"
        :disabled="!username || !password"
      >
        {{ submitting ? 'Signing in…' : 'Sign in' }}
      </AppButton>
    </form>

    <button
      v-if="emergency && !emergencyOpen"
      type="button"
      class="w-full text-center text-xs text-ink-muted underline hover:text-ink"
      @click="emergencyOpen = true"
    >
      Emergency administrator sign-in
    </button>
  </div>
</template>
