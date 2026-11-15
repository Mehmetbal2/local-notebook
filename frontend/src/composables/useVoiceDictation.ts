import { onBeforeUnmount, ref } from 'vue'
import { transcribeDictation } from '@/services/api'

export type DictationState = 'idle' | 'recording' | 'transcribing'

const MAX_SECONDS = 5 * 60
const TARGET_SAMPLE_RATE = 16000

/** Re-encode any recording the browser can decode as 16 kHz mono WAV, which every ASR service accepts. */
export async function toWav(blob: Blob): Promise<Blob> {
  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  const decoder = new AudioCtx()
  try {
    const decoded = await decoder.decodeAudioData(await blob.arrayBuffer())
    const length = Math.max(1, Math.ceil(decoded.duration * TARGET_SAMPLE_RATE))
    const offline = new OfflineAudioContext(1, length, TARGET_SAMPLE_RATE)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    const samples = (await offline.startRendering()).getChannelData(0)

    const buffer = new ArrayBuffer(44 + samples.length * 2)
    const view = new DataView(buffer)
    const writeText = (offset: number, text: string) => {
      for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
    }
    writeText(0, 'RIFF')
    view.setUint32(4, 36 + samples.length * 2, true)
    writeText(8, 'WAVE')
    writeText(12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, TARGET_SAMPLE_RATE, true)
    view.setUint32(28, TARGET_SAMPLE_RATE * 2, true)
    view.setUint16(32, 2, true)
    view.setUint16(34, 16, true)
    writeText(36, 'data')
    view.setUint32(40, samples.length * 2, true)
    for (let i = 0; i < samples.length; i++) {
      const sample = Math.max(-1, Math.min(1, samples[i]!))
      view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    }
    return new Blob([buffer], { type: 'audio/wav' })
  } finally {
    decoder.close().catch(() => {})
  }
}

/**
 * Record from the microphone and turn the speech into text with the configured ASR service.
 * `onText` receives the transcript; `onError` a message to show.
 */
export function useVoiceDictation(options: { onText: (text: string) => void; onError: (message: string) => void; messages: { permission: string; failed: string; empty: string } }) {
  const state = ref<DictationState>('idle')
  const elapsed = ref(0)
  const supported = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'

  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let chunks: Blob[] = []
  let timer: number | null = null
  let cancelled = false

  function cleanup() {
    if (timer !== null) window.clearInterval(timer)
    timer = null
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
    recorder = null
  }

  async function start() {
    if (!supported || state.value !== 'idle') return
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    } catch {
      options.onError(options.messages.permission)
      return
    }
    chunks = []
    cancelled = false
    recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    }
    recorder.onstop = () => void finish(recorder?.mimeType || 'audio/webm')
    recorder.start()
    elapsed.value = 0
    state.value = 'recording'
    timer = window.setInterval(() => {
      elapsed.value += 1
      if (elapsed.value >= MAX_SECONDS) stop()
    }, 1000)
  }

  function stop() {
    if (state.value !== 'recording' || !recorder) return
    recorder.stop()
  }

  function cancel() {
    if (state.value !== 'recording' || !recorder) return
    cancelled = true
    recorder.stop()
  }

  async function finish(mimeType: string) {
    const recorded = new Blob(chunks, { type: mimeType })
    cleanup()
    chunks = []
    if (cancelled || recorded.size === 0) {
      state.value = 'idle'
      return
    }
    state.value = 'transcribing'
    try {
      const wav = await toWav(recorded).catch(() => recorded)
      const text = (await transcribeDictation(wav)).trim()
      if (text) options.onText(text)
      else options.onError(options.messages.empty)
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      options.onError(typeof detail === 'string' ? detail : options.messages.failed)
    } finally {
      state.value = 'idle'
    }
  }

  onBeforeUnmount(() => {
    cancelled = true
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    cleanup()
  })

  return { state, elapsed, supported, start, stop, cancel }
}
