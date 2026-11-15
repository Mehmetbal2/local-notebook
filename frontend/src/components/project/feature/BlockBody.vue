<template>
  <div class="block-body" dir="auto">
    <template v-for="(group, gi) in groups" :key="gi">
      <ul v-if="group.type === 'list'" class="block-body-list">
        <li
          v-for="(item, li) in group.blocks"
          :key="li"
          :style="{ marginInlineStart: `${(item.extra?.indent || 0) * 18}px` }"
        >
          <BlockParts :parts="item.content_parts" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
        </li>
      </ul>
      <blockquote v-else-if="group.blocks[0]!.block_type === 'quote'" class="block-body-quote">
        <BlockParts :parts="group.blocks[0]!.content_parts" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
      </blockquote>
      <p v-else class="block-body-paragraph">
        <BlockParts :parts="group.blocks[0]!.content_parts" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FeatureCitationRefPart, FeatureTextBlock } from '../../../types'
import BlockParts from './BlockParts.vue'

const props = defineProps<{
  blocks: FeatureTextBlock[]
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()

/** Consecutive list items are rendered as one list. */
const groups = computed(() => {
  const result: Array<{ type: 'list' | 'single'; blocks: FeatureTextBlock[] }> = []
  for (const block of props.blocks) {
    const last = result[result.length - 1]
    if (block.block_type === 'list') {
      if (last?.type === 'list') last.blocks.push(block)
      else result.push({ type: 'list', blocks: [block] })
    } else {
      result.push({ type: 'single', blocks: [block] })
    }
  }
  return result
})
</script>

<style scoped>
.block-body {
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-primary);
}

.block-body-paragraph + .block-body-paragraph,
.block-body-list,
.block-body-quote {
  margin-top: 8px;
}

.block-body-list {
  padding-inline-start: 20px;
}

.block-body-list li + li {
  margin-top: 4px;
}

.block-body-quote {
  padding: 4px 0 4px 12px;
  border-inline-start: 3px solid var(--border-strong);
  color: var(--text-secondary);
}
</style>
