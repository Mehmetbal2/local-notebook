<template>
  <template v-for="(part, index) in parts" :key="index"><span
      v-if="part.type === 'text'"
      class="feature-text"
      v-html="parseInlineMarkdown(part.content || '')"
    ></span><sup
      v-else-if="part.type === 'citation_ref'"
      class="inline-citation"
      :class="{ active: activeCitationNum === part.display_num }"
      :data-segment-id="part.segment_id"
      :data-display-num="part.display_num"
      :title="part.summary"
      @click.stop="emit('citationClick', part)"
    >{{ part.display_num }}</sup></template>
</template>

<script setup lang="ts">
import type { FeatureCitationRefPart, FeatureContentPart } from '../../../types'
import { parseInlineMarkdown } from '../../../utils'

defineProps<{
  parts: FeatureContentPart[]
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()
</script>

<style scoped>
.inline-citation {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  margin: 0 2px;
  background: var(--primary-light);
  color: var(--primary-color);
  border-radius: 9px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
  vertical-align: middle;
  transition: background 0.15s, color 0.15s;
}

.inline-citation:hover,
.inline-citation.active {
  background: var(--primary-color);
  color: #fff;
}
</style>
