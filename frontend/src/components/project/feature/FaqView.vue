<template>
  <div class="faq">
    <div class="faq-toolbar">
      <button class="btn btn-text" type="button" @click="setAll(!allOpen)">
        {{ allOpen ? $t('ui.collapseAll') : $t('ui.expandAll') }}
      </button>
    </div>

    <template v-for="(item, index) in items" :key="index">
      <h3 v-if="item.group && item.group !== items[index - 1]?.group" class="faq-group" dir="auto">{{ item.group }}</h3>
      <section class="faq-item" :class="{ open: open.has(index) }">
        <button
          class="faq-question"
          type="button"
          :aria-expanded="open.has(index)"
          dir="auto"
          @click="toggle(index)"
        >
          <span><BlockParts :parts="item.front" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" /></span>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
            <path d="M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z" />
          </svg>
        </button>
        <div v-if="open.has(index)" class="faq-answer">
          <BlockBody :blocks="item.back" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FeatureCitationRefPart } from '../../../types'
import type { CardItem } from './featureStructure'
import BlockParts from './BlockParts.vue'
import BlockBody from './BlockBody.vue'

const props = defineProps<{
  items: CardItem[]
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()

const open = ref(new Set<number>([0]))
const allOpen = computed(() => open.value.size === props.items.length)

function toggle(index: number) {
  const next = new Set(open.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  open.value = next
}

function setAll(value: boolean) {
  open.value = value ? new Set(props.items.map((_, index) => index)) : new Set()
}

watch(() => props.items, () => { open.value = new Set([0]) })
</script>

<style scoped>
.faq {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 720px;
  margin: 0 auto;
}

.faq-toolbar {
  display: flex;
  justify-content: flex-end;
}

.faq-toolbar .btn {
  height: 32px;
}

.faq-group {
  margin-top: 12px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.faq-item {
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  transition: background var(--duration-base);
}

.faq-item.open {
  background: var(--info-soft);
}

.faq-question {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  background: transparent;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 500;
  line-height: 1.45;
  text-align: start;
  border-radius: var(--radius-md);
}

.faq-question svg {
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform var(--duration-base) var(--ease-standard);
}

.faq-item.open .faq-question svg {
  transform: rotate(180deg);
}

.faq-answer {
  padding: 0 16px 16px;
}
</style>
