<template>
  <div ref="rootEl" class="audio-player" :class="{ compact: compact || narrow }">
    <audio
      ref="audioEl"
      :src="src"
      preload="metadata"
      @loadedmetadata="onLoadedMetadata"
      @durationchange="onDurationChange"
      @timeupdate="onTimeUpdate"
      @play="playing = true"
      @pause="playing = false"
      @ended="playing = false"
      @volumechange="muted = audioEl?.muted ?? false"
      @waiting="buffering = true"
      @playing="buffering = false"
      @canplay="buffering = false"
    ></audio>

    <button
      type="button"
      class="ap-btn ap-play"
      :aria-label="playing ? $t('ui.audioPause') : $t('ui.audioPlay')"
      :title="playing ? $t('ui.audioPause') : $t('ui.audioPlay')"
      @click="togglePlay"
    >
      <svg v-if="playing" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z" /></svg>
      <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M8 5.14v13.72L19 12z" /></svg>
    </button>

    <button
      type="button"
      class="ap-btn ap-skip"
      :aria-label="$t('ui.audioSkipBack', { seconds: SKIP_SECONDS })"
      :title="$t('ui.audioSkipBack', { seconds: SKIP_SECONDS })"
      @click="skip(-SKIP_SECONDS)"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 5V2L7 6l5 4V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z" /><text x="12" y="15.6" text-anchor="middle" font-size="6.4" font-weight="700" font-family="system-ui, sans-serif">{{ SKIP_SECONDS }}</text></svg>
    </button>
    <button
      type="button"
      class="ap-btn ap-skip"
      :aria-label="$t('ui.audioSkipForward', { seconds: SKIP_SECONDS })"
      :title="$t('ui.audioSkipForward', { seconds: SKIP_SECONDS })"
      @click="skip(SKIP_SECONDS)"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 5V2l5 4-5 4V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z" /><text x="12" y="15.6" text-anchor="middle" font-size="6.4" font-weight="700" font-family="system-ui, sans-serif">{{ SKIP_SECONDS }}</text></svg>
    </button>

    <span class="ap-time" aria-hidden="true">{{ formatTime(displayTime) }} / {{ formatTime(duration) }}</span>

    <input
      class="ap-seek"
      type="range"
      min="0"
      :max="duration || 0"
      step="0.1"
      :value="displayTime"
      :disabled="!duration"
      :style="{ '--progress': progressPercent + '%' }"
      :aria-label="$t('ui.audioSeek')"
      :aria-valuetext="`${formatTime(displayTime)} / ${formatTime(duration)}`"
      @input="onSeekInput"
      @change="onSeekCommit"
    />

    <div ref="rateWrap" class="ap-rate">
      <button
        type="button"
        class="ap-rate-btn"
        :class="{ active: rate !== 1 }"
        :aria-label="$t('ui.audioPlaybackSpeed')"
        :title="$t('ui.audioPlaybackSpeed')"
        aria-haspopup="menu"
        :aria-expanded="rateMenuOpen"
        @click="rateMenuOpen = !rateMenuOpen"
      >{{ formatRate(rate) }}</button>
      <div v-if="rateMenuOpen" class="ap-rate-menu" role="menu">
        <button
          v-for="option in RATES"
          :key="option"
          type="button"
          role="menuitemradio"
          :aria-checked="option === rate"
          class="ap-rate-option"
          :class="{ selected: option === rate }"
          @click="setRate(option)"
        >
          <span>{{ option === 1 ? $t('ui.audioNormalSpeed') : formatRate(option) }}</span>
          <svg v-if="option === rate" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" /></svg>
        </button>
      </div>
    </div>

    <button
      type="button"
      class="ap-btn ap-mute"
      :aria-label="muted ? $t('ui.audioUnmute') : $t('ui.audioMute')"
      :title="muted ? $t('ui.audioUnmute') : $t('ui.audioMute')"
      @click="toggleMute"
    >
      <svg v-if="muted" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M16.5 12A4.5 4.5 0 0 0 14 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.8 8.8 0 0 0 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3 3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 0 0 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4 9.91 6.09 12 8.18V4z" /></svg>
      <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" /></svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { locale } from '../../i18n'

const props = withDefaults(defineProps<{
  src: string
  compact?: boolean
}>(), {
  compact: false,
})

const SKIP_SECONDS = 15
const RATES = [0.5, 0.75, 0.85, 0.9, 0.95, 1, 1.1, 1.25, 1.5, 1.75, 2] as const
const RATE_STORAGE_KEY = 'ln.audioPlaybackRate'

const rootEl = ref<HTMLElement | null>(null)
const audioEl = ref<HTMLAudioElement | null>(null)
const narrow = ref(false)
let resizeObserver: ResizeObserver | null = null
const rateWrap = ref<HTMLElement | null>(null)
const playing = ref(false)
const buffering = ref(false)
const muted = ref(false)
const duration = ref(0)
const currentTime = ref(0)
const dragTime = ref<number | null>(null)
const rateMenuOpen = ref(false)
const rate = ref(readStoredRate())

const displayTime = computed(() => dragTime.value ?? currentTime.value)
const progressPercent = computed(() => (duration.value ? Math.min(100, (displayTime.value / duration.value) * 100) : 0))

function readStoredRate(): number {
  try {
    const stored = Number(localStorage.getItem(RATE_STORAGE_KEY))
    return Number.isFinite(stored) && stored >= 0.25 && stored <= 4 ? stored : 1
  } catch {
    return 1
  }
}

function applyRate() {
  const el = audioEl.value
  if (!el) return
  el.playbackRate = rate.value
  el.defaultPlaybackRate = rate.value
}

function setRate(value: number) {
  rate.value = value
  rateMenuOpen.value = false
  applyRate()
  try {
    localStorage.setItem(RATE_STORAGE_KEY, String(value))
  } catch {
    // storage unavailable: the speed still applies for this session
  }
}

function readDuration(el: HTMLAudioElement): number {
  return Number.isFinite(el.duration) && el.duration > 0 ? el.duration : 0
}

function onLoadedMetadata() {
  const el = audioEl.value
  if (!el) return
  duration.value = readDuration(el)
  applyRate()
}

function onDurationChange() {
  if (audioEl.value) duration.value = readDuration(audioEl.value)
}

function onTimeUpdate() {
  if (audioEl.value) currentTime.value = audioEl.value.currentTime
}

function seekTo(seconds: number) {
  const el = audioEl.value
  if (!el) return
  const max = duration.value || readDuration(el)
  const target = Math.max(0, max ? Math.min(seconds, max - 0.05) : seconds)
  // fastSeek is less precise; set currentTime so playback continues exactly where the bar was released.
  el.currentTime = target
  currentTime.value = target
}

function onSeekInput(event: Event) {
  dragTime.value = Number((event.target as HTMLInputElement).value)
}

function onSeekCommit(event: Event) {
  seekTo(Number((event.target as HTMLInputElement).value))
  dragTime.value = null
}

function skip(delta: number) {
  seekTo((audioEl.value?.currentTime ?? currentTime.value) + delta)
}

async function togglePlay() {
  const el = audioEl.value
  if (!el) return
  if (el.paused) {
    applyRate()
    try {
      await el.play()
    } catch (error) {
      console.warn('Audio playback failed:', error)
    }
  } else {
    el.pause()
  }
}

function toggleMute() {
  if (audioEl.value) audioEl.value.muted = !audioEl.value.muted
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

const rateFormatter = computed(() => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 2 }))
function formatRate(value: number): string {
  return `${rateFormatter.value.format(value)}×`
}

function onDocumentPointerDown(event: PointerEvent) {
  if (rateMenuOpen.value && rateWrap.value && !rateWrap.value.contains(event.target as Node)) {
    rateMenuOpen.value = false
  }
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && rateMenuOpen.value) {
    rateMenuOpen.value = false
    event.stopPropagation()
  }
}

// A new file starts from the beginning; the chosen speed carries over.
watch(() => props.src, () => {
  currentTime.value = 0
  duration.value = 0
  dragTime.value = null
  playing.value = false
})

onMounted(() => {
  // Below this width the skip and mute buttons are hidden so the seek bar keeps usable room.
  if (rootEl.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(([entry]) => {
      narrow.value = (entry?.contentRect.width ?? 999) < 340
    })
    resizeObserver.observe(rootEl.value)
  }
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown, true)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown, true)
  audioEl.value?.pause()
})
</script>

<style scoped>
.audio-player {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 48px;
  padding: 4px 8px 4px 4px;
  border-radius: 999px;
  background: var(--bg-white, #fff);
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  color: var(--text-primary);
}

.ap-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  cursor: pointer;
  transition: background var(--duration-fast, 0.15s) var(--ease-standard, ease);
}

.ap-btn:hover {
  background: var(--bg-hover, rgba(0, 0, 0, 0.06));
}

.ap-btn:focus-visible,
.ap-rate-btn:focus-visible,
.ap-seek:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring, 0 0 0 3px rgba(11, 87, 208, 0.35));
}

.ap-play {
  width: 40px;
  height: 40px;
  background: var(--primary-color, #0b57d0);
  color: #fff;
}

.ap-play:hover {
  background: var(--primary-hover, #0842a0);
}

.ap-skip {
  color: var(--text-secondary);
}

.ap-time {
  flex: none;
  min-width: 84px;
  padding: 0 6px;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  text-align: center;
}

.ap-seek {
  --progress: 0%;
  flex: 1 1 auto;
  min-width: 60px;
  height: 20px;
  margin: 0 6px;
  background: transparent;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
}

.ap-seek:disabled {
  cursor: default;
  opacity: 0.5;
}

.ap-seek::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(to right, var(--primary-color, #0b57d0) var(--progress), var(--border-strong, #c4c7c5) var(--progress));
}

.ap-seek::-moz-range-track {
  height: 4px;
  border-radius: 999px;
  background: var(--border-strong, #c4c7c5);
}

.ap-seek::-moz-range-progress {
  height: 4px;
  border-radius: 999px;
  background: var(--primary-color, #0b57d0);
}

.ap-seek::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border: none;
  border-radius: 50%;
  background: var(--primary-color, #0b57d0);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  transition: transform var(--duration-fast, 0.15s);
}

.ap-seek::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: none;
  border-radius: 50%;
  background: var(--primary-color, #0b57d0);
}

.ap-seek:hover::-webkit-slider-thumb,
.ap-seek:active::-webkit-slider-thumb {
  transform: scale(1.2);
}

.ap-rate {
  position: relative;
  flex: none;
}

.ap-rate-btn {
  min-width: 48px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.12));
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}

.ap-rate-btn:hover {
  background: var(--bg-hover, rgba(0, 0, 0, 0.06));
}

.ap-rate-btn.active {
  border-color: transparent;
  background: var(--primary-soft, #d3e3fd);
  color: var(--primary-color, #0b57d0);
}

.ap-rate-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 20;
  min-width: 132px;
  max-height: 320px;
  overflow-y: auto;
  padding: 6px;
  border-radius: var(--radius-md, 12px);
  background: var(--bg-white, #fff);
  box-shadow: var(--shadow-lg, 0 8px 24px rgba(0, 0, 0, 0.16));
  border: 1px solid var(--border-color, rgba(0, 0, 0, 0.08));
  animation: ap-menu-in var(--duration-fast, 0.15s) var(--ease-standard, ease);
}

.ap-rate-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  text-align: left;
  cursor: pointer;
}

.ap-rate-option:hover {
  background: var(--bg-hover, rgba(0, 0, 0, 0.06));
}

.ap-rate-option.selected {
  color: var(--primary-color, #0b57d0);
  font-weight: 600;
}

.ap-mute {
  color: var(--text-secondary);
}

.audio-player.compact .ap-skip,
.audio-player.compact .ap-mute {
  display: none;
}

@keyframes ap-menu-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
</style>
