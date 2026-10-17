<script setup lang="ts">
import { ref, useId, watch } from 'vue'

import { CREDENTIAL_KINDS, KIND_LABEL, type Requirement } from '@/entities/workforce/skills'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useSaveRequirements } from '../model/useSaveRequirements'

const props = defineProps<{ queueId: number; requirements: Requirement[] }>()

interface Row {
  key: number
  kind: string
  name: string
  minPeople: number
}
let next = 0
const rows = ref<Row[]>([])
const save = useSaveRequirements()
const formId = useId()

function reset(): void {
  rows.value = props.requirements.map((r) => ({
    key: next++,
    kind: r.kind,
    name: r.name,
    minPeople: r.minPeople,
  }))
}
watch(() => [props.queueId, props.requirements], reset, { immediate: true })

function submit(): void {
  save.mutate({
    queueId: props.queueId,
    requirements: rows.value
      .filter((r) => r.name.trim() !== '')
      .map((r) => ({ kind: r.kind, name: r.name, minPeople: r.minPeople })),
  })
}
</script>

<template>
  <form class="space-y-3" :aria-labelledby="formId" @submit.prevent="submit">
    <h3 :id="formId" class="text-sm font-semibold text-ink">Edit what this queue requires</h3>
    <ul class="space-y-2">
      <li v-for="(row, i) in rows" :key="row.key" class="flex flex-wrap items-end gap-2">
        <label class="text-xs text-ink-muted">
          Kind
          <select
            v-model="row.kind"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            :aria-label="`Kind of requirement ${i + 1}`"
          >
            <option v-for="k in CREDENTIAL_KINDS" :key="k" :value="k">{{ KIND_LABEL[k] }}</option>
          </select>
        </label>
        <label class="text-xs text-ink-muted">
          Name
          <input
            v-model="row.name"
            maxlength="80"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            :aria-label="`Name of requirement ${i + 1}`"
          />
        </label>
        <label class="text-xs text-ink-muted">
          People on every shift
          <input
            v-model.number="row.minPeople"
            type="number"
            min="1"
            class="mt-1 block w-24 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            :aria-label="`People required for requirement ${i + 1}`"
          />
        </label>
        <AppButton
          variant="ghost"
          :aria-label="`Remove requirement ${i + 1}`"
          @click="rows.splice(i, 1)"
        >
          Remove
        </AppButton>
      </li>
    </ul>
    <div class="flex gap-2">
      <AppButton
        variant="secondary"
        @click="rows.push({ key: next++, kind: 'language', name: '', minPeople: 1 })"
      >
        Add requirement
      </AppButton>
      <AppButton type="submit" :loading="save.isPending.value">Save requirements</AppButton>
    </div>
    <div aria-live="polite">
      <NoticeBox v-if="save.isError.value" tone="danger" data-testid="requirements-error">
        {{ problemMessage(save.error.value) }}
      </NoticeBox>
      <p
        v-else-if="save.isSuccess.value"
        class="text-sm text-ink-muted"
        data-testid="requirements-saved"
      >
        Saved.
      </p>
    </div>
  </form>
</template>
