<template>
  <div ref="rootRef" class="mind-map" :class="{ fullscreen: isFullscreen }">
    <div class="mind-toolbar">
      <button class="mind-tool" type="button" :title="$t('ui.expandAll')" :aria-label="$t('ui.expandAll')" @click="expandAll">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M12 5.83 15.17 9l1.41-1.41L12 3 7.41 7.59 8.83 9 12 5.83zm0 12.34L8.83 15l-1.41 1.41L12 21l4.59-4.59L15.17 15 12 18.17z" />
        </svg>
      </button>
      <button class="mind-tool" type="button" :title="$t('ui.collapseAll')" :aria-label="$t('ui.collapseAll')" @click="collapseAll">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M7.41 18.59 8.83 20 12 16.83 15.17 20l1.41-1.41L12 14l-4.59 4.59zm9.18-13.18L15.17 4 12 7.17 8.83 4 7.41 5.41 12 10l4.59-4.59z" />
        </svg>
      </button>
      <button class="mind-tool" type="button" :title="$t('ui.downloadImage')" :aria-label="$t('ui.downloadImage')" @click="downloadPng">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" />
        </svg>
      </button>
      <button
        class="mind-tool"
        type="button"
        :title="isFullscreen ? $t('ui.exitFullscreen') : $t('ui.fullscreen')"
        :aria-label="isFullscreen ? $t('ui.exitFullscreen') : $t('ui.fullscreen')"
        @click="toggleFullscreen"
      >
        <svg v-if="!isFullscreen" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
        </svg>
        <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z" />
        </svg>
      </button>
    </div>

    <svg
      ref="svgRef"
      class="mind-canvas"
      :class="{ panning: isPanning }"
      role="tree"
      :aria-label="rootLabel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @wheel.prevent="onWheel"
    >
      <g :transform="`translate(${view.x} ${view.y}) scale(${view.scale})`">
        <path
          v-for="edge in edges"
          :key="edge.id"
          class="mind-edge"
          :d="edge.d"
          :stroke="edge.color"
          :opacity="edge.opacity"
        />

        <g
          v-for="item in drawn"
          :key="item.id"
          class="mind-node"
          :class="{ 'is-root': item.depth === 0 }"
          :opacity="item.opacity"
          :transform="`translate(${item.x} ${item.y})`"
          role="treeitem"
          tabindex="0"
          :aria-level="item.depth + 1"
          :aria-expanded="item.childCount > 0 ? !collapsed.has(item.id) : undefined"
          :aria-label="item.fullText"
          @click="onNodeClick(item)"
          @keydown="onNodeKeydown($event, item)"
        >
          <title>{{ item.fullText }} — {{ $t('ui.mindMapClickToAsk') }}</title>
          <rect class="mind-node-box" :width="item.w" :height="item.h" :rx="item.depth === 0 ? 14 : 10" :fill="item.fill" />
          <text
            v-for="(line, li) in item.lines"
            :key="li"
            class="mind-node-text"
            :x="item.rtl ? item.w - PAD_X : PAD_X"
            :y="PAD_Y + (li + 0.78) * item.lineHeight"
            :text-anchor="item.rtl ? 'end' : 'start'"
            :direction="item.rtl ? 'rtl' : 'ltr'"
            :fill="item.textColor"
            :font-size="item.fontSize"
            :font-weight="item.fontWeight"
          >{{ line }}</text>

          <g
            v-if="item.childCount > 0"
            class="mind-toggle"
            :transform="`translate(${item.w} ${item.h / 2})`"
            role="button"
            :aria-label="collapsed.has(item.id) ? $t('ui.expandAll') : $t('ui.collapseAll')"
            @click.stop="onToggleClick(item.id)"
          >
            <circle :r="TOGGLE_R" fill="#ffffff" :stroke="item.lineColor" stroke-width="1.5" />
            <path
              :d="collapsed.has(item.id) ? 'M-2 -4.5 L2.5 0 L-2 4.5' : 'M2 -4.5 L-2.5 0 L2 4.5'"
              fill="none"
              :stroke="item.textColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </g>
        </g>
      </g>
    </svg>

    <div class="mind-zoom">
      <button class="mind-tool" type="button" :title="$t('ui.zoomIn')" :aria-label="$t('ui.zoomIn')" @click="zoomBy(1.2)">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" /></svg>
      </button>
      <button class="mind-tool" type="button" :title="$t('ui.zoomOut')" :aria-label="$t('ui.zoomOut')" @click="zoomBy(1 / 1.2)">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M19 13H5v-2h14v2z" /></svg>
      </button>
      <button class="mind-tool" type="button" :title="$t('ui.fitToView')" :aria-label="$t('ui.fitToView')" @click="fitToView(true)">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M3 5v4h2V5h4V3H5c-1.1 0-2 .9-2 2zm2 10H3v4c0 1.1.9 2 2 2h4v-2H5v-4zm14 4h-4v2h4c1.1 0 2-.9 2-2v-4h-2v4zm0-16h-4v2h4v4h2V5c0-1.1-.9-2-2-2z" />
        </svg>
      </button>
    </div>

    <p class="mind-hint">{{ $t('ui.mindMapHint') }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import type { MindNode } from './featureStructure'
import { partsToText } from './featureStructure'

const props = defineProps<{
  root: MindNode
  title?: string
}>()

const emit = defineEmits<{
  /** A node was chosen: ask about it in the chat. `context` is its parent topic. */
  (e: 'ask', payload: { topic: string; context: string }): void
}>()

// ---------- Geometry ----------
const PAD_X = 14
const PAD_Y = 10
const TOGGLE_R = 11
const GAP_X = 64
const GAP_Y = 12
const MAX_TEXT = 160
const ANIM_MS = 280

interface Palette { fill: string; soft: string; text: string; line: string }

/** One hue per main branch, so a branch reads as a unit however deep it goes. */
const PALETTES: Palette[] = [
  { fill: '#d3e3fd', soft: '#e8f0fe', text: '#041e49', line: '#8ab4f8' },
  { fill: '#c4eed0', soft: '#e6f4ea', text: '#0d3b1e', line: '#81c995' },
  { fill: '#fde7b0', soft: '#fef6dd', text: '#4a3200', line: '#f2c14e' },
  { fill: '#e9ddff', soft: '#f3edff', text: '#2a1065', line: '#bba2f5' },
  { fill: '#c0efed', soft: '#e0f7f6', text: '#003d3a', line: '#6fd3cc' },
  { fill: '#fdd5df', soft: '#fdecf0', text: '#4d0b1d', line: '#f093ad' },
]
const ROOT_STYLE = { fill: '#0b57d0', text: '#ffffff', line: '#8ab4f8' }

interface NodeInfo {
  id: string
  depth: number
  branch: number
  fullText: string
  parentId: string | null
  childIds: string[]
}

interface Measured { lines: string[]; w: number; h: number; lineHeight: number; fontSize: number; fontWeight: number; rtl: boolean }

interface Placed extends Measured { id: string; depth: number; x: number; y: number }

interface Drawn extends Placed {
  opacity: number
  childCount: number
  fullText: string
  fill: string
  textColor: string
  lineColor: string
}

const rootRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const isFullscreen = ref(false)
const collapsed = ref(new Set<string>())
const view = reactive({ x: 0, y: 0, scale: 1 })
const size = reactive({ w: 0, h: 0 })

/** Flattened, cleaned tree. Rebuilt when a new map is shown. */
const infos = shallowRef(new Map<string, NodeInfo>())
const rootId = computed(() => props.root.id)
const rootLabel = computed(() => infos.value.get(rootId.value)?.fullText || props.title || '')

function cleanText(raw: string): string {
  const text = raw.replace(/\*\*|__|`/g, '').replace(/\s+/g, ' ').trim()
  return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT - 1).trimEnd()}…` : text
}

function buildInfos(root: MindNode) {
  const map = new Map<string, NodeInfo>()
  const walk = (node: MindNode, depth: number, branch: number, parentId: string | null) => {
    map.set(node.id, {
      id: node.id,
      depth,
      branch,
      fullText: cleanText(partsToText(node.parts)) || '—',
      parentId,
      childIds: node.children.map((child) => child.id),
    })
    node.children.forEach((child, index) => walk(child, depth + 1, depth === 0 ? index : branch, node.id))
  }
  walk(root, 0, 0, null)
  infos.value = map
}

// ---------- Text measuring ----------
let measureCtx: CanvasRenderingContext2D | null = null
const measureCache = new Map<string, Measured>()
const fontFamily = ref('sans-serif')

function styleFor(depth: number) {
  if (depth === 0) return { size: 15, weight: 500, lineHeight: 21, maxW: 240 }
  if (depth === 1) return { size: 13.5, weight: 600, lineHeight: 19, maxW: 250 }
  return { size: 13, weight: 400, lineHeight: 18, maxW: 260 }
}

function wrap(text: string, maxWidth: number): string[] {
  const ctx = measureCtx!
  const lines: string[] = []
  let line = ''
  for (const word of text.split(' ')) {
    const candidate = line ? `${line} ${word}` : word
    if (ctx.measureText(candidate).width <= maxWidth) {
      line = candidate
      continue
    }
    if (line) lines.push(line)
    // A single word wider than the box is broken by characters.
    line = ''
    for (const char of word) {
      if (ctx.measureText(line + char).width > maxWidth && line) {
        lines.push(line)
        line = char
      } else {
        line += char
      }
    }
  }
  if (line) lines.push(line)
  return lines.length ? lines : ['']
}

function measure(info: NodeInfo): Measured {
  const key = `${info.id}:${info.depth}`
  const cached = measureCache.get(key)
  if (cached) return cached

  const style = styleFor(info.depth)
  if (!measureCtx) measureCtx = document.createElement('canvas').getContext('2d')
  measureCtx!.font = `${style.weight} ${style.size}px ${fontFamily.value}`
  const lines = wrap(info.fullText, style.maxW - PAD_X * 2)
  const textWidth = Math.max(...lines.map((line) => measureCtx!.measureText(line).width))
  const result: Measured = {
    lines,
    w: Math.ceil(Math.min(style.maxW, textWidth + PAD_X * 2 + 4)),
    h: Math.ceil(lines.length * style.lineHeight + PAD_Y * 2),
    lineHeight: style.lineHeight,
    fontSize: style.size,
    fontWeight: style.weight,
    rtl: /^[^A-Za-zÀ-ɏ]*[֐-ࣿ]/.test(info.fullText),
  }
  measureCache.set(key, result)
  return result
}

// ---------- Layout ----------
function visibleChildren(id: string): string[] {
  if (collapsed.value.has(id)) return []
  return infos.value.get(id)?.childIds || []
}

/** Left-to-right tidy tree: one column per depth, parents centred on their children. */
function computeLayout(): Map<string, Placed> {
  const placed = new Map<string, Placed>()
  const columnWidth: number[] = []

  const collectWidths = (id: string) => {
    const info = infos.value.get(id)!
    const m = measure(info)
    columnWidth[info.depth] = Math.max(columnWidth[info.depth] || 0, m.w)
    visibleChildren(id).forEach(collectWidths)
  }
  collectWidths(rootId.value)

  const columnX: number[] = [0]
  for (let d = 1; d < columnWidth.length; d++) {
    columnX[d] = columnX[d - 1]! + columnWidth[d - 1]! + GAP_X
  }

  const place = (id: string, top: number): number => {
    const info = infos.value.get(id)!
    const m = measure(info)
    const children = visibleChildren(id)
    const x = columnX[info.depth]!

    if (children.length === 0) {
      placed.set(id, { ...m, id, depth: info.depth, x, y: top })
      return top + m.h
    }

    let cursor = top
    children.forEach((childId, index) => {
      if (index > 0) cursor += GAP_Y
      cursor = place(childId, cursor)
    })
    const first = placed.get(children[0]!)!
    const last = placed.get(children[children.length - 1]!)!
    let y = (first.y + first.h / 2 + last.y + last.h / 2) / 2 - m.h / 2

    // A parent taller than its children's span pushes the subtree down instead of overlapping above.
    if (y < top) {
      const shift = top - y
      const shiftSubtree = (cid: string) => {
        const p = placed.get(cid)!
        p.y += shift
        visibleChildren(cid).forEach(shiftSubtree)
      }
      children.forEach(shiftSubtree)
      cursor += shift
      y = top
    }

    placed.set(id, { ...m, id, depth: info.depth, x, y })
    return Math.max(cursor, y + m.h)
  }
  place(rootId.value, 0)
  return placed
}

// ---------- Animated state ----------
const shown = shallowRef(new Map<string, Placed>())
const opacityOf = shallowRef(new Map<string, number>())
let target = new Map<string, Placed>()
let animFrame = 0

function easeOut(t: number) {
  return 1 - Math.pow(1 - t, 3)
}

/**
 * Moves every node from where it is drawn now to its new place. New nodes grow out of
 * their parent's old position. `anchorId` keeps that node fixed on screen.
 */
function relayout(options: { animate?: boolean; anchorId?: string } = {}) {
  const from = new Map(shown.value)
  const next = computeLayout()
  target = next

  const fromView = { x: view.x, y: view.y }
  let toView = { ...fromView }
  if (options.anchorId) {
    const before = from.get(options.anchorId)
    const after = next.get(options.anchorId)
    if (before && after) {
      toView = {
        x: fromView.x - (after.x - before.x) * view.scale,
        y: fromView.y - (after.y - before.y) * view.scale,
      }
    }
  }

  const start = new Map<string, Placed>()
  for (const [id, p] of next) {
    const existing = from.get(id)
    if (existing) {
      start.set(id, existing)
    } else {
      const parentId = infos.value.get(id)?.parentId
      const origin = (parentId && from.get(parentId)) || p
      start.set(id, { ...p, x: origin.x + (origin === p ? 0 : origin.w - p.w / 2), y: origin.y + origin.h / 2 - p.h / 2 })
    }
  }

  cancelAnimationFrame(animFrame)
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (!options.animate || reduceMotion || from.size === 0) {
    shown.value = next
    opacityOf.value = new Map([...next.keys()].map((id) => [id, 1]))
    view.x = toView.x
    view.y = toView.y
    return
  }

  const begin = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, (now - begin) / ANIM_MS)
    const k = easeOut(t)
    const frame = new Map<string, Placed>()
    const opacity = new Map<string, number>()
    for (const [id, p] of next) {
      const s = start.get(id)!
      frame.set(id, { ...p, x: s.x + (p.x - s.x) * k, y: s.y + (p.y - s.y) * k })
      opacity.set(id, from.has(id) ? 1 : k)
    }
    shown.value = frame
    opacityOf.value = opacity
    view.x = fromView.x + (toView.x - fromView.x) * k
    view.y = fromView.y + (toView.y - fromView.y) * k
    if (t < 1) animFrame = requestAnimationFrame(step)
  }
  animFrame = requestAnimationFrame(step)
}

function colorsFor(id: string) {
  const info = infos.value.get(id)!
  if (info.depth === 0) return { fill: ROOT_STYLE.fill, text: ROOT_STYLE.text, line: ROOT_STYLE.line }
  const palette = PALETTES[info.branch % PALETTES.length]!
  return { fill: info.depth === 1 ? palette.fill : palette.soft, text: palette.text, line: palette.line }
}

const drawn = computed<Drawn[]>(() =>
  [...shown.value.values()].map((p) => {
    const info = infos.value.get(p.id)!
    const colors = colorsFor(p.id)
    return {
      ...p,
      opacity: opacityOf.value.get(p.id) ?? 1,
      childCount: info.childIds.length,
      fullText: info.fullText,
      fill: colors.fill,
      textColor: colors.text,
      lineColor: colors.line,
    }
  }),
)

function edgePath(parent: Placed, child: Placed): string {
  const x1 = parent.x + parent.w + TOGGLE_R
  const y1 = parent.y + parent.h / 2
  const x2 = child.x
  const y2 = child.y + child.h / 2
  const mx = (x1 + x2) / 2
  return `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`
}

const edges = computed(() => {
  const list: Array<{ id: string; d: string; color: string; opacity: number }> = []
  for (const child of shown.value.values()) {
    const parentId = infos.value.get(child.id)?.parentId
    const parent = parentId ? shown.value.get(parentId) : undefined
    if (!parent) continue
    list.push({
      id: child.id,
      d: edgePath(parent, child),
      color: colorsFor(child.id).line,
      opacity: opacityOf.value.get(child.id) ?? 1,
    })
  }
  return list
})

// ---------- Expand / collapse ----------
function toggle(id: string) {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
  relayout({ animate: true, anchorId: id })
}

function branchIds(minDepth: number): string[] {
  return [...infos.value.values()].filter((info) => info.childIds.length > 0 && info.depth >= minDepth).map((info) => info.id)
}

function expandAll() {
  collapsed.value = new Set()
  relayout({ animate: true, anchorId: rootId.value })
}

/** Back to the overview: the centre and its main topics. */
function collapseAll() {
  collapsed.value = new Set(branchIds(1))
  relayout({ animate: true, anchorId: rootId.value })
}

// ---------- Viewport ----------
function bounds(placed: Map<string, Placed>) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of placed.values()) {
    minX = Math.min(minX, p.x)
    minY = Math.min(minY, p.y)
    maxX = Math.max(maxX, p.x + p.w + TOGGLE_R * 2)
    maxY = Math.max(maxY, p.y + p.h)
  }
  return { minX, minY, maxX, maxY }
}

function fitToView(animate = false) {
  if (!size.w || !size.h || target.size === 0) return
  const b = bounds(target)
  const margin = 40
  const scale = Math.max(0.3, Math.min(1.1, (size.w - margin * 2) / (b.maxX - b.minX), (size.h - margin * 2) / (b.maxY - b.minY)))
  const x = (size.w - (b.maxX - b.minX) * scale) / 2 - b.minX * scale
  const y = (size.h - (b.maxY - b.minY) * scale) / 2 - b.minY * scale
  if (!animate) {
    Object.assign(view, { x, y, scale })
    return
  }
  const from = { ...view }
  const begin = performance.now()
  const step = (now: number) => {
    const k = easeOut(Math.min(1, (now - begin) / ANIM_MS))
    view.x = from.x + (x - from.x) * k
    view.y = from.y + (y - from.y) * k
    view.scale = from.scale + (scale - from.scale) * k
    if (k < 1) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

function zoomAt(factor: number, cx: number, cy: number) {
  const scale = Math.min(2.5, Math.max(0.25, view.scale * factor))
  const real = scale / view.scale
  view.x = cx - (cx - view.x) * real
  view.y = cy - (cy - view.y) * real
  view.scale = scale
}

function zoomBy(factor: number) {
  zoomAt(factor, size.w / 2, size.h / 2)
}

/** Scrolling pans like a page; pinch or Ctrl/Cmd + scroll zooms around the pointer. */
function onWheel(event: WheelEvent) {
  if (event.ctrlKey || event.metaKey) {
    const rect = svgRef.value!.getBoundingClientRect()
    zoomAt(Math.exp(-event.deltaY * 0.01), event.clientX - rect.left, event.clientY - rect.top)
  } else {
    view.x -= event.deltaX
    view.y -= event.deltaY
  }
}

// Dragging anywhere pans; a press that does not move is a click.
const isPanning = ref(false)
let drag: { id: number; x: number; y: number; vx: number; vy: number; moved: boolean } | null = null
let suppressClick = false

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0) return
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, vx: view.x, vy: view.y, moved: false }
}

function onPointerMove(event: PointerEvent) {
  if (!drag || drag.id !== event.pointerId) return
  const dx = event.clientX - drag.x
  const dy = event.clientY - drag.y
  if (!drag.moved && Math.hypot(dx, dy) < 4) return
  if (!drag.moved) {
    drag.moved = true
    isPanning.value = true
    svgRef.value?.setPointerCapture(event.pointerId)
  }
  view.x = drag.vx + dx
  view.y = drag.vy + dy
}

function onPointerUp(event: PointerEvent) {
  if (!drag || drag.id !== event.pointerId) return
  suppressClick = drag.moved
  if (drag.moved) svgRef.value?.releasePointerCapture(event.pointerId)
  drag = null
  isPanning.value = false
  // Clicks fire after pointerup; reset once they have been seen.
  setTimeout(() => { suppressClick = false }, 0)
}

// ---------- Node actions ----------
function ask(id: string) {
  const info = infos.value.get(id)
  if (!info) return
  const parent = info.parentId ? infos.value.get(info.parentId) : undefined
  emit('ask', { topic: info.fullText, context: parent?.fullText || '' })
}

function onNodeClick(item: Drawn) {
  if (suppressClick) return
  ask(item.id)
}

function onToggleClick(id: string) {
  if (suppressClick) return
  toggle(id)
}

function onNodeKeydown(event: KeyboardEvent, item: Drawn) {
  if (event.key === 'Enter') {
    event.preventDefault()
    ask(item.id)
  } else if (event.key === ' ' && item.childCount > 0) {
    event.preventDefault()
    toggle(item.id)
  } else if (event.key === 'ArrowRight' && item.childCount > 0 && collapsed.value.has(item.id)) {
    event.preventDefault()
    toggle(item.id)
  } else if (event.key === 'ArrowLeft' && item.childCount > 0 && !collapsed.value.has(item.id)) {
    event.preventDefault()
    toggle(item.id)
  }
}

// ---------- Fullscreen ----------
function toggleFullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void rootRef.value?.requestFullscreen?.()
}

function onFullscreenChange() {
  isFullscreen.value = document.fullscreenElement === rootRef.value
}

// ---------- PNG export ----------
function escapeXml(value: string) {
  return value.replace(/[<>&"']/g, (char) => `&#${char.charCodeAt(0)};`)
}

/** Draws the map as it is currently expanded, at 2x, on a white background. */
async function downloadPng() {
  const placed = target
  if (placed.size === 0) return
  const b = bounds(placed)
  const margin = 32
  const width = Math.ceil(b.maxX - b.minX + margin * 2)
  const height = Math.ceil(b.maxY - b.minY + margin * 2)
  const ox = margin - b.minX
  const oy = margin - b.minY

  const parts: string[] = []
  for (const child of placed.values()) {
    const parentId = infos.value.get(child.id)?.parentId
    const parent = parentId ? placed.get(parentId) : undefined
    if (parent) parts.push(`<path d="${edgePath(parent, child)}" fill="none" stroke="${colorsFor(child.id).line}" stroke-width="1.6"/>`)
  }
  for (const p of placed.values()) {
    const info = infos.value.get(p.id)!
    const c = colorsFor(p.id)
    const text = p.lines
      .map((line, i) => `<text x="${p.rtl ? p.w - PAD_X : PAD_X}" y="${PAD_Y + (i + 0.78) * p.lineHeight}" text-anchor="${p.rtl ? 'end' : 'start'}" direction="${p.rtl ? 'rtl' : 'ltr'}" fill="${c.text}" font-size="${p.fontSize}" font-weight="${p.fontWeight}">${escapeXml(line)}</text>`)
      .join('')
    const toggleMark = info.childIds.length > 0
      ? `<g transform="translate(${p.w} ${p.h / 2})"><circle r="${TOGGLE_R}" fill="#fff" stroke="${c.line}" stroke-width="1.5"/><path d="${collapsed.value.has(p.id) ? 'M-2 -4.5 L2.5 0 L-2 4.5' : 'M2 -4.5 L-2.5 0 L2 4.5'}" fill="none" stroke="${c.text}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></g>`
      : ''
    parts.push(`<g transform="translate(${p.x} ${p.y})"><rect width="${p.w}" height="${p.h}" rx="${p.depth === 0 ? 14 : 10}" fill="${c.fill}"/>${text}${toggleMark}</g>`)
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="${escapeXml(fontFamily.value)}"><rect width="100%" height="100%" fill="#ffffff"/><g transform="translate(${ox} ${oy})">${parts.join('')}</g></svg>`
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }))

  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('Mind map image could not be rendered'))
      image.src = url
    })
    const ratio = Math.min(2, 16000 / Math.max(width, height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(width * ratio)
    canvas.height = Math.round(height * ratio)
    const ctx = canvas.getContext('2d')!
    ctx.scale(ratio, ratio)
    ctx.drawImage(image, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('PNG export failed')
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${(rootLabel.value || 'mind-map').replace(/[\\/:*?"<>|\u0000-\u001f]+/g, ' ').trim().slice(0, 80) || 'mind-map'}.png`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  } catch (error) {
    console.error(error)
  } finally {
    URL.revokeObjectURL(url)
  }
}

// ---------- Lifecycle ----------
let resizeObserver: ResizeObserver | null = null
let fitted = false

function showMap(root: MindNode) {
  measureCache.clear()
  buildInfos(root)
  // Opens like NotebookLM: the centre and its main topics; deeper levels on demand.
  collapsed.value = new Set(branchIds(1))
  shown.value = new Map()
  fitted = false
  relayout()
  if (size.w) {
    fitToView()
    fitted = true
  }
}

watch(() => props.root, showMap)

onMounted(async () => {
  fontFamily.value = getComputedStyle(document.body).fontFamily || 'sans-serif'
  await document.fonts?.ready
  showMap(props.root)

  resizeObserver = new ResizeObserver(([entry]) => {
    if (!entry) return
    size.w = entry.contentRect.width
    size.h = entry.contentRect.height
    if (!fitted && size.w > 0) {
      fitToView()
      fitted = true
    }
  })
  await nextTick()
  if (svgRef.value) resizeObserver.observe(svgRef.value)
  document.addEventListener('fullscreenchange', onFullscreenChange)
})

onUnmounted(() => {
  cancelAnimationFrame(animFrame)
  resizeObserver?.disconnect()
  document.removeEventListener('fullscreenchange', onFullscreenChange)
})

watch(isFullscreen, () => nextTick(() => setTimeout(() => fitToView(true), 60)))
</script>

<style scoped>
.mind-map {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 420px;
  background: var(--bg-white);
  overflow: hidden;
}

.mind-map.fullscreen {
  background: #ffffff;
}

.mind-canvas {
  flex: 1;
  width: 100%;
  min-height: 0;
  cursor: grab;
  touch-action: none;
  user-select: none;
}

.mind-canvas.panning {
  cursor: grabbing;
}

.mind-edge {
  fill: none;
  stroke-width: 1.6;
}

.mind-node {
  cursor: pointer;
  outline: none;
}

.mind-node-box {
  transition: filter var(--duration-fast);
}

.mind-node:hover > .mind-node-box {
  filter: brightness(0.95) saturate(1.15);
}

.mind-node:focus-visible > .mind-node-box {
  stroke: var(--primary-color);
  stroke-width: 2.5;
}

.mind-node-text {
  pointer-events: none;
  font-family: inherit;
}

.mind-toggle {
  cursor: pointer;
}

.mind-toggle:hover circle {
  fill: #f1f3f4;
}

.mind-toolbar {
  position: absolute;
  top: 12px;
  inset-inline-end: 12px;
  z-index: 2;
  display: flex;
  gap: 2px;
  padding: 4px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(6px);
}

.mind-zoom {
  position: absolute;
  bottom: 16px;
  inset-inline-end: 12px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: var(--shadow-md);
}

.mind-tool {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
}

.mind-tool:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.mind-hint {
  position: absolute;
  bottom: 16px;
  inset-inline-start: 16px;
  z-index: 1;
  max-width: calc(100% - 90px);
  padding: 6px 12px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.9);
  color: var(--text-tertiary);
  font-size: 12px;
  pointer-events: none;
}
</style>
