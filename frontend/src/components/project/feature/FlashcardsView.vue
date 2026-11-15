<template>
  <div class="flashcards" tabindex="0" @keydown="handleKeydown">
    <div class="deck-toolbar">
      <span class="deck-progress">{{ position + 1 }} / {{ order.length }}</span>
      <span v-if="known.size > 0" class="deck-known">{{ $t('ui.knownCount', { count: known.size }) }}</span>
      <span class="deck-spacer"></span>
      <button class="deck-tool" type="button" :title="$t('ui.shuffleCards')" :aria-label="$t('ui.shuffleCards')" @click="shuffle">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
          <path d="M10.59 9.17 5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z" />
        </svg>
      </button>
      <button class="deck-tool" type="button" :title="$t('ui.restartDeck')" :aria-label="$t('ui.restartDeck')" @click="restart">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
          <path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z" />
        </svg>
      </button>
    </div>

    <div class="deck-track" aria-hidden="true">
      <div class="deck-track-fill" :style="{ width: `${((position + 1) / order.length) * 100}%` }"></div>
    </div>

    <div
      class="card"
      :class="{ flipped, known: known.has(currentIndex) }"
      role="button"
      tabindex="0"
      :aria-label="$t('ui.flipHint')"
      @click="flipped = !flipped"
      @keydown.enter.self.prevent="flipped = !flipped"
    >
      <div class="card-inner">
        <div class="card-face card-front" dir="auto">
          <span class="card-label">{{ current.group || $t('ui.cardFront') }}</span>
          <div class="card-question">
            <BlockParts :parts="current.front" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
          </div>
          <span class="card-hint">{{ $t('ui.flipHint') }}</span>
        </div>
        <div class="card-face card-back" dir="auto">
          <span class="card-label">{{ $t('ui.cardBack') }}</span>
          <div class="card-answer">
            <BlockBody :blocks="current.back" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
          </div>
        </div>
      </div>
    </div>

    <div class="deck-nav">
      <button class="btn btn-outline" type="button" :disabled="position === 0" @click="go(-1)">
        {{ $t('ui.previousCard') }}
      </button>
      <button class="btn" :class="known.has(currentIndex) ? 'btn-outline' : 'btn-tonal'" type="button" @click="toggleKnown">
        {{ known.has(currentIndex) ? $t('ui.markUnknown') : $t('ui.markKnown') }}
      </button>
      <button class="btn btn-filled" type="button" :disabled="position === order.length - 1" @click="go(1)">
        {{ $t('ui.nextCard') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FeatureCitationRefPart } from '../../../types'
import type { CardItem } from './featureStructure'
import BlockParts from './BlockParts.vue'
import BlockBody from './BlockBody.vue'

const props = defineProps<{
  cards: CardItem[]
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()

const order = ref<number[]>([])
const position = ref(0)
const flipped = ref(false)
const known = ref(new Set<number>())

const currentIndex = computed(() => order.value[position.value] ?? 0)
const current = computed(() => props.cards[currentIndex.value]!)

function restart() {
  order.value = props.cards.map((_, index) => index)
  position.value = 0
  flipped.value = false
  known.value = new Set()
}

function shuffle() {
  const next = [...order.value]
  for (let i = next.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[next[i], next[j]] = [next[j]!, next[i]!]
  }
  order.value = next
  position.value = 0
  flipped.value = false
}

function go(step: number) {
  const next = position.value + step
  if (next < 0 || next >= order.value.length) return
  position.value = next
  flipped.value = false
}

function toggleKnown() {
  const next = new Set(known.value)
  if (next.has(currentIndex.value)) next.delete(currentIndex.value)
  else next.add(currentIndex.value)
  known.value = next
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowRight') go(1)
  else if (event.key === 'ArrowLeft') go(-1)
  else if (event.key === ' ') {
    event.preventDefault()
    flipped.value = !flipped.value
  }
}

watch(() => props.cards, restart, { immediate: true })
</script>

<style scoped>
.flashcards {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 620px;
  margin: 0 auto;
  outline: none;
}

.deck-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.deck-progress {
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.deck-known {
  color: var(--success-color);
}

.deck-spacer {
  flex: 1;
}

.deck-tool {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
}

.deck-tool:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.deck-track {
  height: 4px;
  border-radius: 2px;
  background: var(--bg-tertiary);
  overflow: hidden;
}

.deck-track-fill {
  height: 100%;
  border-radius: 2px;
  background: var(--primary-color);
  transition: width var(--duration-slow) var(--ease-emphasized);
}

.card {
  perspective: 1400px;
  height: clamp(260px, 46vh, 420px);
  cursor: pointer;
  border-radius: var(--radius-xl);
}

.card-inner {
  position: relative;
  display: grid;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform 0.5s var(--ease-emphasized);
}

.card.flipped .card-inner {
  transform: rotateY(180deg);
}

.card-face {
  grid-area: 1 / 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  padding: 24px 28px;
  border-radius: var(--radius-xl);
  overflow: hidden;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.card-front {
  background: var(--primary-soft);
  color: var(--on-primary-soft);
}

.card-back {
  background: var(--bg-white);
  box-shadow: inset 0 0 0 1px var(--border-color), var(--shadow-md);
  transform: rotateY(180deg);
}

.card.known .card-front {
  background: var(--success-soft);
}

.card-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  opacity: 0.7;
}

.card-question {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  align-items: safe center;
  justify-content: center;
  text-align: center;
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 500;
  line-height: 1.35;
}

.card-answer {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  justify-content: safe center;
  font-size: 15px;
}

.card-hint {
  font-size: 12px;
  text-align: center;
  opacity: 0.6;
}

.deck-nav {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.deck-nav .btn {
  flex: 1;
  padding: 0 12px;
}

@media (prefers-reduced-motion: reduce) {
  .card-inner {
    transition: none;
  }
}
</style>
