<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'

/** An accessible modal. Focus moves in and is trapped, Escape and a click on the backdrop close
 * it, focus returns to what opened it, and the page behind does not scroll. On a phone it becomes
 * a bottom sheet. The caller owns `open` (v-model:open). */
const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    subtitle?: string
    size?: 'sm' | 'md'
    /** Keep the title for screen readers only (the command palette has its own layout). */
    titleHidden?: boolean
  }>(),
  { size: 'md', subtitle: undefined, titleHidden: false },
)
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const uid = useId()
const titleId = `dialog-title-${uid}`
const descId = `dialog-desc-${uid}`
const panel = ref<HTMLElement | null>(null)
const body = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null
let previousOverflow = ''

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function focusables(): HTMLElement[] {
  return Array.from(panel.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
}

function close(): void {
  emit('update:open', false)
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    close()
    return
  }
  if (e.key !== 'Tab' || !panel.value) return
  const items = focusables()
  if (items.length === 0) {
    e.preventDefault()
    panel.value.focus()
    return
  }
  const first = items[0] as HTMLElement
  const last = items[items.length - 1] as HTMLElement
  const active = document.activeElement
  if (e.shiftKey && (active === first || active === panel.value)) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  } else if (!panel.value.contains(active)) {
    e.preventDefault()
    first.focus()
  }
}

function release(): void {
  document.removeEventListener('keydown', onKey, true)
  document.body.style.overflow = previousOverflow
  const back = opener
  opener = null
  if (back && document.contains(back)) back.focus()
}

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      previousOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      document.addEventListener('keydown', onKey, true)
      await nextTick()
      // The first control in the body (a field to type in) beats the close button above it.
      const target =
        panel.value?.querySelector<HTMLElement>('[data-autofocus]') ??
        body.value?.querySelector<HTMLElement>(FOCUSABLE) ??
        focusables()[0]
      ;(target ?? panel.value)?.focus()
    } else {
      release()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (props.open) release()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6"
      >
        <div
          class="absolute inset-0 bg-ink/40"
          data-testid="dialog-backdrop"
          aria-hidden="true"
          @click="close"
        />
        <div
          ref="panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
          :aria-describedby="subtitle ? descId : undefined"
          tabindex="-1"
          class="dialog-panel relative flex max-h-[90vh] w-full flex-col rounded-t-3xl bg-surface shadow-[var(--shadow-pop)] outline-none sm:rounded-3xl"
          :class="size === 'sm' ? 'sm:max-w-md' : 'sm:max-w-2xl'"
        >
          <header
            class="flex items-start justify-between gap-4 px-6 pt-6"
            :class="titleHidden ? 'sr-only' : ''"
          >
            <div>
              <h2 :id="titleId" class="text-xl font-semibold tracking-tight text-ink">
                {{ title }}
              </h2>
              <p v-if="subtitle" :id="descId" class="mt-1 text-sm text-ink-muted">
                {{ subtitle }}
              </p>
            </div>
            <button
              v-if="!titleHidden"
              type="button"
              class="-mr-2 -mt-1 inline-flex size-10 items-center justify-center rounded-xl text-ink-muted hover:bg-surface-muted hover:text-ink"
              aria-label="Close"
              @click="close"
            >
              <X :size="18" aria-hidden="true" />
            </button>
          </header>
          <div ref="body" class="quiet-scroll min-h-0 flex-1 overflow-y-auto px-6 py-5">
            <slot />
          </div>
          <footer
            v-if="$slots.footer"
            class="flex flex-wrap items-center justify-end gap-2 border-t border-line px-6 py-4"
          >
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
