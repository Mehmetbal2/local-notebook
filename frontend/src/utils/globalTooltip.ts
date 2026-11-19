/**
 * One tooltip for every element with a `data-tooltip` attribute.
 *
 * The tooltip lives directly under <body> with fixed positioning, so scrolling panels and
 * `overflow: hidden` containers can no longer cut it off. It sits above the element, moves
 * below when there is no room, and is kept inside the window horizontally; the arrow keeps
 * pointing at the element. Works for mouse hover and keyboard focus, and reads the attribute
 * when shown, so tooltips whose text changes stay current.
 */
const MARGIN = 8
const GAP = 8
const SHOW_DELAY_MS = 120

let tip: HTMLDivElement | null = null
let text: HTMLSpanElement | null = null
let current: HTMLElement | null = null
let showTimer: number | undefined

function ensureTip(): HTMLDivElement {
  if (tip) return tip
  tip = document.createElement('div')
  tip.className = 'app-tooltip'
  tip.setAttribute('role', 'tooltip')
  tip.id = 'app-tooltip'
  text = document.createElement('span')
  tip.appendChild(text)
  document.body.appendChild(tip)
  return tip
}

function targetFrom(node: EventTarget | null): HTMLElement | null {
  if (!(node instanceof Element)) return null
  const el = node.closest<HTMLElement>('[data-tooltip]')
  return el && el.dataset.tooltip?.trim() ? el : null
}

function place(el: HTMLElement) {
  const box = ensureTip()
  const rect = el.getBoundingClientRect()
  const tipRect = box.getBoundingClientRect()
  const viewportWidth = document.documentElement.clientWidth
  const viewportHeight = document.documentElement.clientHeight

  let top = rect.top - tipRect.height - GAP
  let below = false
  if (top < MARGIN && rect.bottom + GAP + tipRect.height <= viewportHeight - MARGIN) {
    top = rect.bottom + GAP
    below = true
  }
  const center = rect.left + rect.width / 2
  const maxLeft = Math.max(MARGIN, viewportWidth - tipRect.width - MARGIN)
  const left = Math.min(Math.max(center - tipRect.width / 2, MARGIN), maxLeft)
  const arrow = Math.min(Math.max(center - left, 12), tipRect.width - 12)

  box.style.top = `${Math.round(top)}px`
  box.style.left = `${Math.round(left)}px`
  box.style.setProperty('--arrow-x', `${Math.round(arrow)}px`)
  box.classList.toggle('below', below)
}

function show(el: HTMLElement) {
  const label = el.dataset.tooltip?.trim()
  if (!label) return
  const box = ensureTip()
  current = el
  text!.textContent = label
  box.classList.remove('visible')
  box.style.top = '-9999px'
  box.style.left = '-9999px'
  // Measure at the final size, then position and fade in.
  requestAnimationFrame(() => {
    if (current !== el || !el.isConnected) return
    place(el)
    box.classList.add('visible')
    el.setAttribute('aria-describedby', box.id)
  })
}

function hide() {
  window.clearTimeout(showTimer)
  showTimer = undefined
  if (current?.getAttribute('aria-describedby') === 'app-tooltip') {
    current.removeAttribute('aria-describedby')
  }
  current = null
  tip?.classList.remove('visible')
}

function scheduleShow(el: HTMLElement) {
  if (current === el) return
  hide()
  showTimer = window.setTimeout(() => show(el), SHOW_DELAY_MS)
}

export function installGlobalTooltip() {
  if (typeof document === 'undefined') return

  document.addEventListener('pointerover', (event) => {
    if ((event as PointerEvent).pointerType === 'touch') return
    const el = targetFrom(event.target)
    if (el) scheduleShow(el)
  })
  document.addEventListener('pointerout', (event) => {
    const el = targetFrom(event.target)
    if (!el) return
    const next = (event as PointerEvent).relatedTarget
    if (next instanceof Node && el.contains(next)) return
    hide()
  })
  document.addEventListener('focusin', (event) => {
    const el = targetFrom(event.target)
    if (el && (event.target as HTMLElement).matches?.(':focus-visible')) scheduleShow(el)
  })
  document.addEventListener('focusout', hide)
  document.addEventListener('pointerdown', hide, true)
  document.addEventListener('scroll', hide, true)
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') hide()
  })
  window.addEventListener('blur', hide)
  window.addEventListener('resize', hide)
}
