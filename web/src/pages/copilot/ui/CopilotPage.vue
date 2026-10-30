<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import { computed, nextTick, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useSessionStore, type Role } from '@/entities/session'
import { ApiProblem } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

import { askCopilot } from '../api/copilot'
import { COPILOT_MAX_QUESTION, type CopilotAction, type CopilotSource } from '../model/types'

const screen = NAV_ITEMS.find((item) => item.key === 'copilot')
const session = useSessionStore()

// Until the first answer comes back, offer a few questions for the role. After that the chips are
// whatever the API says this role can ask (it is the authority; this list is only a starting point).
const STARTERS: Record<Role, string[]> = {
  agent: ['What is my schedule next week?', 'What is my leave balance?'],
  lead: ['Who in my team has pending leave?', 'Who in my team is on shift tomorrow?'],
  planner: ['Which queue has the biggest gap on Tuesday?', 'Why is Tuesday short?'],
  admin: ['Which queue has the biggest gap on Tuesday?', 'What is the forecast status?'],
  executive: ['How many people are rostered this week?', 'What is the absence rate?'],
  customer_ops: ['How many contracts do I have?'],
}

type Message =
  | { id: number; kind: 'me'; text: string }
  | {
      id: number
      kind: 'copilot'
      text: string
      refused: boolean
      sources: CopilotSource[]
      actions: CopilotAction[]
    }
  | { id: number; kind: 'error'; text: string }

// The conversation lives in this component and nowhere else: not in storage, not on the server.
const messages = ref<Message[]>([])
const suggestions = ref<string[]>(session.user ? STARTERS[session.user.role] : [])
const draft = ref('')
const waiting = ref(false)
const composer = ref<HTMLTextAreaElement | null>(null)
let nextId = 1

const remaining = computed(() => COPILOT_MAX_QUESTION - draft.value.length)
const canSend = computed(
  () => !waiting.value && draft.value.trim().length > 0 && remaining.value >= 0,
)

/** Only addresses inside this app become links; anything else the API sent is dropped. */
function safe(actions: CopilotAction[]): CopilotAction[] {
  return actions.filter((a) => a.path.startsWith('/') && !a.path.startsWith('//'))
}

function describeFailure(error: unknown): string {
  if (error instanceof ApiProblem) {
    if (error.status === 429)
      return error.detail || 'You have asked a lot of questions. Wait a minute.'
    if (error.code === 'feature.disabled') return 'The Copilot is not part of your plan.'
    if (error.status === 403) return 'Your role may not use the Copilot.'
    if (error.status === 404) return 'The Copilot is not available here.'
    if (error.status === 422) return 'That question could not be read. Try a shorter one.'
  }
  return 'The Copilot could not answer just now. Try again.'
}

async function ask(text: string): Promise<void> {
  const question = text.trim()
  if (!question || waiting.value || question.length > COPILOT_MAX_QUESTION) return
  messages.value.push({ id: nextId++, kind: 'me', text: question })
  draft.value = ''
  waiting.value = true
  try {
    const answer = await askCopilot(question)
    messages.value.push({
      id: nextId++,
      kind: 'copilot',
      text: answer.answer,
      refused: answer.refused,
      sources: answer.sources,
      actions: safe(answer.actions),
    })
    if (answer.suggestions.length > 0) suggestions.value = answer.suggestions
  } catch (error) {
    messages.value.push({ id: nextId++, kind: 'error', text: describeFailure(error) })
  } finally {
    waiting.value = false
    await nextTick()
    composer.value?.focus() // back to the composer, ready for the next question
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void ask(draft.value)
  }
}
</script>

<template>
  <PageHeader eyebrow="Insight" :title="screen?.label ?? 'Copilot'" :subtitle="screen?.subtitle" />

  <section
    class="mt-4 flex min-h-96 flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)] sm:p-6"
    aria-label="Conversation"
  >
    <div
      class="flex flex-1 flex-col gap-3"
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      data-testid="conversation"
    >
      <p v-if="messages.length === 0" class="text-sm text-ink-muted">
        Ask a question about your own work, or pick one below.
      </p>

      <template v-for="message in messages" :key="message.id">
        <div v-if="message.kind === 'me'" class="flex justify-end">
          <p
            class="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-brand px-4 py-2 text-sm text-brand-contrast"
            data-testid="my-message"
          >
            {{ message.text }}
          </p>
        </div>

        <div v-else-if="message.kind === 'copilot'" class="flex">
          <div
            class="page-enter max-w-[90%] rounded-2xl border border-line px-4 py-3 text-sm"
            :class="message.refused ? 'bg-surface-muted text-ink-muted' : 'bg-brand-soft text-ink'"
            :data-testid="message.refused ? 'refusal' : 'answer'"
          >
            <p class="whitespace-pre-wrap">{{ message.text }}</p>
            <p
              v-for="source in message.sources"
              :key="source.tool"
              class="mt-2 text-xs text-ink-muted"
              data-testid="based-on"
            >
              Based on: {{ source.tool }} ({{ source.rows }}
              {{ source.rows === 1 ? 'row' : 'rows' }})
            </p>
            <div v-if="message.actions.length > 0" class="mt-3 flex flex-wrap gap-2">
              <RouterLink
                v-for="action in message.actions"
                :key="action.path + action.label"
                :to="action.path"
                class="press inline-flex min-h-11 items-center rounded-xl border border-line bg-surface px-4 text-sm font-semibold text-ink hover:bg-surface-muted sm:min-h-10"
                data-testid="open-action"
              >
                {{ action.label }}
              </RouterLink>
            </div>
          </div>
        </div>

        <NoticeBox v-else tone="warn" data-testid="copilot-error">{{ message.text }}</NoticeBox>
      </template>

      <div
        v-if="waiting"
        class="flex items-center gap-2 text-sm text-ink-muted"
        data-testid="typing"
      >
        <span class="flex gap-1" aria-hidden="true">
          <span
            v-for="n in 3"
            :key="n"
            class="size-2 rounded-full bg-ink-muted motion-safe:animate-pulse"
            :style="{ animationDelay: `${n * 150}ms` }"
          />
        </span>
        <span class="sr-only">The Copilot is working on it</span>
      </div>
    </div>

    <div
      v-if="suggestions.length > 0"
      class="flex flex-wrap gap-2"
      aria-label="Suggested questions"
    >
      <button
        v-for="suggestion in suggestions"
        :key="suggestion"
        type="button"
        class="press inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface-muted px-4 text-sm text-ink hover:bg-brand-soft disabled:opacity-60 sm:min-h-9"
        :disabled="waiting"
        data-testid="suggestion"
        @click="ask(suggestion)"
      >
        <Sparkles class="size-4 text-brand-ink" aria-hidden="true" />
        {{ suggestion }}
      </button>
    </div>

    <form class="flex flex-col gap-2" @submit.prevent="ask(draft)">
      <label for="copilot-question" class="text-sm font-medium text-ink">Your question</label>
      <textarea
        id="copilot-question"
        ref="composer"
        v-model="draft"
        rows="2"
        :maxlength="COPILOT_MAX_QUESTION + 50"
        class="w-full resize-y rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink"
        aria-describedby="copilot-count"
        @keydown="onKeydown"
      />
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p
          id="copilot-count"
          class="text-xs"
          :class="remaining < 0 ? 'text-danger' : 'text-ink-muted'"
          data-testid="char-count"
        >
          {{ draft.length }} of {{ COPILOT_MAX_QUESTION }} characters
          <span v-if="remaining < 0">: too long, shorten it to ask</span>
        </p>
        <AppButton type="submit" :disabled="!canSend" :loading="waiting">Ask</AppButton>
      </div>
    </form>
  </section>
</template>
