<template>
  <ol class="timeline">
    <template v-for="(entry, index) in entries" :key="index">
      <li v-if="entry.group && entry.group !== entries[index - 1]?.group" class="timeline-group" dir="auto">
        {{ entry.group }}
      </li>
      <li class="timeline-entry">
        <span class="timeline-dot" aria-hidden="true"></span>
        <div class="timeline-card" dir="auto">
          <span class="timeline-label">{{ entry.label }}</span>
          <h4 class="timeline-title">
            <BlockParts :parts="entry.title" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
          </h4>
          <BlockBody
            v-if="entry.body.length > 0"
            :blocks="entry.body"
            :active-citation-num="activeCitationNum"
            @citation-click="emit('citationClick', $event)"
          />
        </div>
      </li>
    </template>
  </ol>
</template>

<script setup lang="ts">
import type { FeatureCitationRefPart } from '../../../types'
import type { TimelineEntry } from './featureStructure'
import BlockParts from './BlockParts.vue'
import BlockBody from './BlockBody.vue'

defineProps<{
  entries: TimelineEntry[]
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()
</script>

<style scoped>
.timeline {
  position: relative;
  max-width: 720px;
  margin: 0 auto;
  padding-inline-start: 28px;
  list-style: none;
}

.timeline::before {
  content: '';
  position: absolute;
  inset-block: 8px;
  inset-inline-start: 7px;
  width: 2px;
  border-radius: 1px;
  background: var(--border-color);
}

.timeline-group {
  position: relative;
  margin: 20px 0 10px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.timeline-group:first-child {
  margin-top: 0;
}

.timeline-entry {
  position: relative;
  padding-bottom: 14px;
}

.timeline-dot {
  position: absolute;
  top: 18px;
  inset-inline-start: -28px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-white);
  border: 4px solid var(--primary-color);
}

.timeline-card {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  transition: background var(--duration-base);
}

.timeline-entry:hover .timeline-card {
  background: var(--info-soft);
}

.timeline-label {
  display: inline-block;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: var(--primary-soft);
  color: var(--on-primary-soft);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.timeline-title {
  margin: 8px 0 6px;
  font-size: 16px;
  font-weight: 500;
  line-height: 1.35;
}
</style>
