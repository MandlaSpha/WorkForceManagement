<script setup lang="ts">
/** Dev-only shortcut listing the synthetic demo accounts from `manage.py seed_demo`.
 * Rendered only when VITE_DEMO_LOGINS=1; the password comes from VITE_DEMO_PASSWORD, never from
 * the source, so nothing sensitive ships in a production build. */
const emit = defineEmits<{ pick: [username: string, password: string] }>()

const enabled = import.meta.env.VITE_DEMO_LOGINS === '1'
const password: string = import.meta.env.VITE_DEMO_PASSWORD ?? ''

const accounts = [
  { username: 'planner', blurb: 'Planner — full scheduling' },
  { username: 'lead', blurb: 'Team lead — approvals' },
  { username: 'agent', blurb: 'Agent — own schedule & leave' },
  { username: 'admin', blurb: 'Admin — everything' },
  { username: 'executive', blurb: 'Executive — read-only dashboards' },
  { username: 'customerops', blurb: 'Customer operations — own contracts' },
] as const
</script>

<template>
  <section
    v-if="enabled"
    class="rounded-xl border border-line bg-surface p-4"
    aria-label="Demo logins"
  >
    <h2 class="text-xs font-semibold text-ink-muted">Demo logins · click to fill</h2>
    <ul class="mt-2 space-y-1">
      <li v-for="a in accounts" :key="a.username">
        <button
          type="button"
          class="flex w-full items-center justify-between rounded-md px-2 py-1 text-left text-xs hover:bg-surface-muted"
          @click="emit('pick', a.username, password)"
        >
          <code class="font-mono text-ink">{{ a.username }}</code>
          <span class="text-ink-muted">{{ a.blurb }}</span>
        </button>
      </li>
    </ul>
  </section>
</template>
