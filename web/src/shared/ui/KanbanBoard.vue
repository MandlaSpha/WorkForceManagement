<script setup lang="ts" generic="T extends { id: number }">
import { ChevronDown } from 'lucide-vue-next'
import { nextTick, ref } from 'vue'

/** A board of stages with cards that move between them. It knows nothing of swaps or leave: the
 * page says which cards sit in which column, whether a move is legal (with the reason when it is
 * not), and what to do when one is asked for. Every move has two ways in: dragging the card, and
 * the "Move to..." button on it, which works from a keyboard, a screen reader or a thumb. */
export interface KanbanColumn<Item> {
  key: string
  label: string
  /** Tailwind background class for the coloured dot. */
  dot: string
  items: Item[]
  /** The column's total next to its count, e.g. "6 days". */
  total?: string
  /** What an empty column says. */
  empty: string
}
export type MoveCheck = { ok: true } | { ok: false; reason: string }

const props = defineProps<{
  columns: ReadonlyArray<KanbanColumn<T>>
  /** Names the board for people who cannot see it. */
  label: string
  loading?: boolean
  /** A short name for a card, used in button names and announcements. */
  itemLabel: (item: T) => string
  /** Can this card be moved at all by this person? (An agent's cards cannot.) */
  movable: (item: T) => boolean
  /** May this card go to that column, and if not, why not. */
  canMove: (item: T, to: string) => MoveCheck
  /** What the live region says (the page words the outcome of each move). */
  announcement?: string
}>()
const emit = defineEmits<{ move: [item: T, to: string] }>()

// A long column shows its first cards and asks before showing the rest.
const SHOWN = 6
const expanded = ref<ReadonlySet<string>>(new Set())
function visible(c: KanbanColumn<T>): T[] {
  return expanded.value.has(c.key) ? c.items : c.items.slice(0, SHOWN)
}
function showAll(key: string): void {
  expanded.value = new Set([...expanded.value, key])
}

const dragging = ref<T | null>(null)
const over = ref<string | null>(null)
const menuFor = ref<number | null>(null)
const root = ref<HTMLElement | null>(null)

function columnOf(item: T): string | undefined {
  return props.columns.find((c) => c.items.some((i) => i.id === item.id))?.key
}

function check(to: string): MoveCheck | null {
  const item = dragging.value
  if (!item || columnOf(item) === to) return null
  return props.canMove(item, to)
}

function onDragStart(event: DragEvent, item: T): void {
  dragging.value = item
  menuFor.value = null
  event.dataTransfer?.setData('text/plain', String(item.id)) // Firefox starts no drag without it
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
function onDragEnd(): void {
  dragging.value = null
  over.value = null
}
function onDragOver(event: DragEvent, to: string): void {
  const verdict = check(to)
  over.value = to
  if (verdict?.ok) {
    event.preventDefault() // this is a place the card may land
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  }
}
function onDrop(event: DragEvent, to: string): void {
  const item = dragging.value
  const verdict = check(to)
  event.preventDefault()
  onDragEnd()
  if (item && verdict?.ok) emit('move', item, to)
}

function choose(item: T, to: string): void {
  menuFor.value = null
  emit('move', item, to)
}

function onMenuKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    const id = menuFor.value
    menuFor.value = null
    event.stopPropagation()
    if (id !== null) void focusCard(id)
  }
}

/** Put focus on a card's Move button once the card has settled in its new column. */
async function focusCard(id: number): Promise<void> {
  await nextTick()
  root.value?.querySelector<HTMLElement>(`[data-card-id="${id}"] [data-move-button]`)?.focus()
}
defineExpose({ focusCard })
</script>

<template>
  <div ref="root" class="space-y-3">
    <p class="sr-only" role="status" aria-live="polite" data-testid="kanban-live">
      {{ announcement }}
    </p>

    <div
      class="quiet-scroll -mx-1 flex snap-x snap-mandatory gap-4 overflow-x-auto px-1 pb-2 lg:snap-none"
      role="group"
      :aria-label="label"
      data-testid="kanban"
    >
      <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -- dropping is the shortcut; the Move to button is the accessible path -->
      <section
        v-for="c in columns"
        :key="c.key"
        class="kanban-column flex min-w-[82%] flex-1 snap-start flex-col rounded-3xl border bg-surface-muted p-3 sm:min-w-[18rem] lg:min-w-0"
        :class="
          over === c.key && check(c.key)?.ok
            ? 'border-brand ring-2 ring-brand/40'
            : over === c.key && check(c.key)
              ? 'border-danger'
              : 'border-line'
        "
        :aria-labelledby="`kanban-h-${c.key}`"
        :data-testid="`kanban-col-${c.key}`"
        :data-drop="over === c.key && check(c.key)?.ok ? 'yes' : undefined"
        @dragover="onDragOver($event, c.key)"
        @dragleave="over = over === c.key ? null : over"
        @drop="onDrop($event, c.key)"
      >
        <header class="mb-3 flex items-center gap-2 px-1">
          <span class="size-2.5 shrink-0 rounded-full" :class="c.dot" aria-hidden="true" />
          <h3 :id="`kanban-h-${c.key}`" class="min-w-0 flex-1 text-sm font-semibold text-ink">
            {{ c.label }}
          </h3>
          <span
            class="rounded-full bg-surface px-2 py-0.5 text-xs font-semibold tabular-nums text-ink"
            :data-testid="`kanban-count-${c.key}`"
            >{{ c.items.length }}</span
          >
          <span
            v-if="c.total"
            class="text-xs tabular-nums text-ink-muted"
            :data-testid="`kanban-total-${c.key}`"
            >{{ c.total }}</span
          >
        </header>

        <p
          v-if="over === c.key && check(c.key) && !check(c.key)?.ok"
          class="mb-2 rounded-xl bg-danger-soft px-3 py-2 text-xs font-medium text-danger"
          data-testid="kanban-not-allowed"
        >
          Not allowed here:
          {{ (check(c.key) as { reason: string }).reason }}
        </p>

        <ul v-if="loading" class="space-y-3" :aria-label="`Loading ${c.label}`" aria-busy="true">
          <li v-for="n in 2" :key="n" class="skeleton h-24 rounded-2xl bg-surface" />
        </ul>
        <ul v-else-if="c.items.length > 0" class="space-y-3" :aria-label="c.label">
          <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -- dragging is the shortcut; the Move to button is the accessible path -->
          <li
            v-for="item in visible(c)"
            :key="item.id"
            class="kanban-card relative rounded-2xl border border-line bg-surface p-3 shadow-[var(--shadow-card)]"
            :class="[
              dragging?.id === item.id ? 'kanban-lifted' : '',
              movable(item) ? 'cursor-grab' : '',
            ]"
            :draggable="movable(item)"
            :data-card-id="item.id"
            :data-testid="`kanban-card-${item.id}`"
            @dragstart="onDragStart($event, item)"
            @dragend="onDragEnd"
          >
            <slot name="card" :item="item" :column="c.key" />

            <div v-if="movable(item)" class="mt-3 flex justify-end">
              <button
                type="button"
                data-move-button
                class="press inline-flex min-h-10 items-center gap-1 rounded-full border border-line bg-surface px-3 text-xs font-semibold text-ink hover:bg-surface-muted"
                aria-haspopup="true"
                :aria-expanded="menuFor === item.id"
                :aria-label="`Move ${itemLabel(item)} to…`"
                @click="menuFor = menuFor === item.id ? null : item.id"
                @keydown="onMenuKey"
              >
                Move to…
                <ChevronDown :size="14" aria-hidden="true" />
              </button>
            </div>
            <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -- Escape closes the menu; the buttons inside are the controls -->
            <ul
              v-if="menuFor === item.id"
              class="mt-2 space-y-1 rounded-xl border border-line bg-surface-muted p-2"
              :aria-label="`Move ${itemLabel(item)} to`"
              @keydown="onMenuKey"
            >
              <template v-for="target in columns" :key="target.key">
                <li v-if="target.key !== c.key">
                  <button
                    type="button"
                    class="flex min-h-10 w-full flex-col items-start rounded-lg px-3 py-1.5 text-left text-sm hover:bg-surface disabled:cursor-not-allowed disabled:opacity-70"
                    :disabled="!canMove(item, target.key).ok"
                    :data-testid="`kanban-move-${item.id}-${target.key}`"
                    @click="choose(item, target.key)"
                  >
                    <span class="font-medium text-ink">{{ target.label }}</span>
                    <span v-if="!canMove(item, target.key).ok" class="text-xs text-ink-muted">{{
                      (canMove(item, target.key) as { reason: string }).reason
                    }}</span>
                  </button>
                </li>
              </template>
            </ul>
          </li>
        </ul>
        <button
          v-if="!loading && c.items.length > SHOWN && !expanded.has(c.key)"
          type="button"
          class="press mt-3 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm font-medium text-brand-ink"
          :data-testid="`kanban-more-${c.key}`"
          @click="showAll(c.key)"
        >
          Show {{ c.items.length - SHOWN }} more
        </button>
        <p
          v-else-if="!loading && c.items.length === 0"
          class="rounded-2xl border border-dashed border-line px-3 py-6 text-center text-sm text-ink-muted"
          :data-testid="`kanban-empty-${c.key}`"
        >
          {{ c.empty }}
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
@media (prefers-reduced-motion: no-preference) {
  .kanban-card {
    animation: kanban-settle 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
    transition:
      box-shadow 0.15s ease,
      transform 0.15s ease;
  }
  .kanban-lifted {
    transform: rotate(1.5deg) scale(1.02);
  }
  .kanban-column {
    transition:
      box-shadow 0.15s ease,
      border-color 0.15s ease;
  }
}
.kanban-lifted {
  box-shadow: var(--shadow-pop);
  opacity: 0.9;
}
@keyframes kanban-settle {
  from {
    transform: translateY(-6px) scale(1.02);
    box-shadow: var(--shadow-pop);
  }
  to {
    transform: none;
  }
}
</style>
