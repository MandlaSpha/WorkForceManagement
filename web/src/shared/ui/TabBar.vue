<script setup lang="ts">
export interface Tab {
  key: string
  label: string
}

const props = defineProps<{
  tabs: ReadonlyArray<Tab>
  /** Names the group of tabs for people who cannot see it. */
  label: string
  /** Prefix for the element ids: the tab is `${idPrefix}-tab-${key}`, its panel should be
   * `${idPrefix}-panel-${key}` so the two point at each other. */
  idPrefix: string
}>()
const model = defineModel<string>({ required: true })

/** Arrow keys, Home and End move between tabs, as the tabs pattern asks. Only the chosen tab is
 * in the tab order; the others are reached with the arrows. */
function onKey(event: KeyboardEvent): void {
  const index = props.tabs.findIndex((t) => t.key === model.value)
  const last = props.tabs.length - 1
  const target =
    event.key === 'ArrowRight'
      ? (index + 1) % props.tabs.length
      : event.key === 'ArrowLeft'
        ? (index - 1 + props.tabs.length) % props.tabs.length
        : event.key === 'Home'
          ? 0
          : event.key === 'End'
            ? last
            : -1
  if (target < 0) return
  event.preventDefault()
  const key = props.tabs[target]!.key
  model.value = key
  // Focus goes to the target itself, not to whichever tab is marked selected a moment later: a
  // page may update the chosen tab asynchronously (the address), and focus must not wait for it.
  document.getElementById(`${props.idPrefix}-tab-${key}`)?.focus()
}
</script>

<template>
  <div class="flex gap-1 overflow-x-auto border-b border-line" role="tablist" :aria-label="label">
    <button
      v-for="t in tabs"
      :id="`${idPrefix}-tab-${t.key}`"
      :key="t.key"
      type="button"
      role="tab"
      class="-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium"
      :class="
        model === t.key
          ? 'border-brand text-brand-ink'
          : 'border-transparent text-ink-muted hover:text-ink'
      "
      :aria-selected="model === t.key"
      :aria-controls="`${idPrefix}-panel-${t.key}`"
      :tabindex="model === t.key ? 0 : -1"
      @click="model = t.key"
      @keydown="onKey"
    >
      {{ t.label }}
    </button>
  </div>
</template>
