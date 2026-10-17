<script setup lang="ts">
/** Dev-only shortcut listing the synthetic demo accounts from `manage.py seed_demo`.
 * Rendered only when VITE_DEMO_LOGINS=1; the password comes from VITE_DEMO_PASSWORD, never from
 * the source, so nothing sensitive ships in a production build. */
const emit = defineEmits<{ pick: [username: string, password: string] }>()

const enabled = import.meta.env.VITE_DEMO_LOGINS === '1'
const password: string = import.meta.env.VITE_DEMO_PASSWORD ?? ''

const groups = [
  {
    title: 'Staff',
    accounts: [
      { username: 'planner', blurb: 'Planner — full scheduling' },
      { username: 'admin', blurb: 'Admin — everything' },
      { username: 'executive', blurb: 'Executive — read-only dashboards' },
      { username: 'customerops', blurb: 'Customer operations — own contracts' },
    ],
  },
  {
    title: 'Team 1',
    accounts: [
      { username: 'lead', blurb: 'Team lead — approvals' },
      { username: 'agent', blurb: 'Agent' },
      { username: 'agent2', blurb: 'Agent' },
      { username: 'agent3', blurb: 'Agent' },
      { username: 'agent4', blurb: 'Agent' },
      { username: 'agent5', blurb: 'Agent' },
    ],
  },
  {
    title: 'Team 2',
    accounts: [
      { username: 'lead2', blurb: 'Team lead — approvals' },
      { username: 'agent6', blurb: 'Agent' },
      { username: 'agent7', blurb: 'Agent' },
      { username: 'agent8', blurb: 'Agent' },
      { username: 'agent9', blurb: 'Agent' },
      { username: 'agent10', blurb: 'Agent' },
    ],
  },
] as const
</script>

<template>
  <section
    v-if="enabled"
    class="rounded-xl border border-line bg-surface p-4"
    aria-label="Demo logins"
  >
    <h2 class="text-xs font-semibold text-ink-muted">Demo logins · click to sign in</h2>
    <div v-for="g in groups" :key="g.title" class="mt-2">
      <h3 class="px-2 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
        {{ g.title }}
      </h3>
      <ul class="mt-1 space-y-0.5">
        <li v-for="a in g.accounts" :key="a.username">
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
    </div>
  </section>
</template>
