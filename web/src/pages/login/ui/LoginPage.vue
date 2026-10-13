<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { homePathFor, type SessionUser } from '@/entities/session'
import {
  DemoLogins,
  fetchProviders,
  LOCAL_ONLY,
  SignInForm,
  type SignInProvider,
} from '@/features/sign-in'
import { ThemeToggle } from '@/features/toggle-theme'
import { safeRedirect } from '@/shared/lib/redirect'
import BrandMark from '@/shared/ui/BrandMark.vue'

const route = useRoute()
const router = useRouter()
const form = ref<InstanceType<typeof SignInForm> | null>(null)
const providers = ref<readonly SignInProvider[]>(LOCAL_ONLY)
const loaded = ref(false)

// Where the user was heading; the same-site check also runs on the server before it is used.
const next = safeRedirect(route.query.redirect, '/')

onMounted(async () => {
  providers.value = await fetchProviders()
  loaded.value = true
})

async function onSignedIn(user: SessionUser): Promise<void> {
  await router.push(safeRedirect(route.query.redirect, homePathFor(user.role)))
}
</script>

<template>
  <div class="flex min-h-dvh flex-col items-center bg-canvas px-4 py-12">
    <div class="absolute right-4 top-4"><ThemeToggle /></div>

    <main class="w-full max-w-sm space-y-6">
      <div>
        <BrandMark />
        <h1 class="mt-3 text-lg font-semibold text-ink">Workforce Management</h1>
        <p class="text-[10px] font-medium uppercase tracking-wider text-ink-muted">
          Technology people
        </p>
      </div>

      <section class="rounded-2xl border border-line bg-surface p-6 shadow-sm">
        <SignInForm
          ref="form"
          :providers="providers"
          :sso-error="route.query.error"
          :next="next"
          @signed-in="onSignedIn"
        />
      </section>

      <DemoLogins v-if="loaded" @pick="(u, p) => form?.fill(u, p)" />

      <p class="text-center text-[11px] text-ink-muted">
        A proudly South African company focused on customer service.
      </p>
    </main>
  </div>
</template>
