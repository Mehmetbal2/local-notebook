<template>
  <div class="podcast">
    <div v-if="audioUrl" class="podcast-player">
      <div class="podcast-player-head">
        <span class="podcast-player-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z" />
          </svg>
        </span>
        <div class="podcast-player-meta">
          <strong dir="auto">{{ title }}</strong>
          <span>{{ $t('ui.podcastTurns', { count: turns.length }) }}<template v-if="caption"> · {{ caption }}</template></span>
        </div>
        <a class="podcast-download" :href="audioUrl" download :title="$t('ui.downloadAudio')" :aria-label="$t('ui.downloadAudio')">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
            <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" />
          </svg>
        </a>
      </div>
      <AudioPlayer :src="audioUrl" class="podcast-audio" />
    </div>

    <h3 class="podcast-transcript-title">{{ $t('ui.podcastTranscript') }}</h3>
    <ol class="podcast-turns">
      <li v-for="(turn, index) in turns" :key="index" class="podcast-turn" :class="turn.speaker === 'HOST' ? 'is-host' : 'is-guest'">
        <span class="podcast-avatar" aria-hidden="true">{{ speakerLabel(turn.speaker).charAt(0) }}</span>
        <div class="podcast-bubble" dir="auto">
          <span class="podcast-speaker">{{ speakerLabel(turn.speaker) }}</span>
          <p>
            <BlockParts :parts="turn.parts" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
          </p>
        </div>
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
import type { FeatureCitationRefPart } from '../../../types'
import type { DialogueTurn } from './featureStructure'
import BlockParts from './BlockParts.vue'
import AudioPlayer from '../../common/AudioPlayer.vue'
import { t } from '../../../i18n'

defineProps<{
  turns: DialogueTurn[]
  title: string
  audioUrl?: string
  caption?: string
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()

function speakerLabel(speaker: DialogueTurn['speaker']): string {
  return speaker === 'HOST' ? t('ui.podcastHost') : t('ui.podcastGuest')
}
</script>

<style scoped>
.podcast {
  max-width: 760px;
  margin: 0 auto;
}

.podcast-player {
  position: sticky;
  top: -1px;
  z-index: 2;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, #fde7f1 0%, #e8f0fe 100%);
  box-shadow: var(--shadow-sm);
}

.podcast-player-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.podcast-player-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #be123c;
  color: #fff;
  flex-shrink: 0;
}

.podcast-player-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.podcast-player-meta strong {
  font-size: 15px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.podcast-player-meta span {
  font-size: 12px;
  color: var(--text-tertiary);
}

.podcast-download {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  color: var(--text-secondary);
}

.podcast-download:hover {
  background: rgba(255, 255, 255, 0.7);
  color: var(--text-primary);
}

.podcast-audio {
  width: 100%;
}

.podcast-transcript-title {
  margin: 22px 0 12px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.podcast-turns {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.podcast-turn {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.podcast-turn.is-guest {
  flex-direction: row-reverse;
}

.podcast-avatar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: #0b57d0;
}

.is-guest .podcast-avatar {
  background: #be123c;
}

.podcast-bubble {
  max-width: 84%;
  padding: 10px 14px 12px;
  border-radius: 18px;
  background: var(--info-soft);
  font-size: 14px;
  line-height: 1.65;
}

.is-host .podcast-bubble {
  border-top-left-radius: 6px;
}

.is-guest .podcast-bubble {
  border-top-right-radius: 6px;
  background: #fdecf0;
}

.podcast-speaker {
  display: block;
  margin-bottom: 2px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: #0b57d0;
}

.is-guest .podcast-speaker {
  color: #be123c;
}
</style>
