// Arabic, Persian and Hebrew in HTML that Word opens as a .doc: Word draws those letters with
// the Latin font (Calibri) unless they are marked as right-to-left text with a font that
// has the glyphs, and they then show up as empty boxes.

const RTL_CHARS = '\\u0590-\\u08FF\\uFB1D-\\uFDFF\\uFE70-\\uFEFF'
const RTL_CHAR = new RegExp(`[${RTL_CHARS}]`)
const RTL_SPAN = new RegExp(
  // Sentence punctuation right after the Arabic belongs to it, so it shows at the Arabic end.
  `[${RTL_CHARS}](?:[${RTL_CHARS}\\s.,:;!?()\\[\\]«»"'“”‘’\\-–—/…]*[${RTL_CHARS}])?(?:[.,:;!?؟…]+)?`,
  'g',
)
const LETTER = /\p{L}/gu
const RTL_FONT = "'Times New Roman'"
const BLOCKS = 'p, li, h1, h2, h3, h4, h5, h6, td, th'

/**
 * Block direction by its first letter (Unicode's first-strong rule, like dir="auto"): a reference
 * line or Turkish sentence quoting Arabic stays left-to-right; an Arabic paragraph turns right-to-left.
 */
function startsRtl(text: string): boolean {
  const first = text.match(LETTER)?.[0]
  return !!first && RTL_CHAR.test(first)
}

/** Wrap right-to-left stretches in spans Word understands and mark mostly-RTL blocks. */
export function markRtlForWord(html: string): string {
  if (!RTL_CHAR.test(html)) return html
  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html')

  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  while (walker.nextNode()) textNodes.push(walker.currentNode as Text)

  for (const node of textNodes) {
    const text = node.data
    if (!RTL_CHAR.test(text)) continue
    const fragment = doc.createDocumentFragment()
    let position = 0
    for (const match of text.matchAll(RTL_SPAN)) {
      const start = match.index ?? 0
      if (start > position) fragment.append(text.slice(position, start))
      const span = doc.createElement('span')
      span.setAttribute('lang', 'AR-SA')
      span.setAttribute('dir', 'rtl')
      span.setAttribute('style', `font-family:${RTL_FONT};mso-bidi-font-family:${RTL_FONT}`)
      span.textContent = match[0]
      fragment.append(span)
      position = start + match[0].length
    }
    if (position < text.length) fragment.append(text.slice(position))
    node.replaceWith(fragment)
  }

  for (const block of Array.from(doc.body.querySelectorAll(BLOCKS))) {
    if (startsRtl(block.textContent || '')) {
      block.setAttribute('dir', 'rtl')
      block.setAttribute('style', `${block.getAttribute('style') || ''};text-align:right`)
    }
  }
  return doc.body.innerHTML
}
