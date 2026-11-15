/**
 * HTML sanitiser for content rendered with v-html.
 *
 * Model output, document text and parsed table markup are untrusted: Markdown
 * lets raw HTML through, so without this a document or a model reply could run
 * script in the user's session. The markup is parsed into an inert document,
 * dangerous elements are dropped and every attribute that can execute code or
 * load a non-http resource is removed. KaTeX output (spans, inline styles,
 * MathML, SVG paths) and citation markers (class / data-* attributes) pass through.
 */

const BLOCKED_TAGS = new Set([
  'script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet',
  'link', 'meta', 'base', 'form', 'input', 'button', 'textarea', 'select', 'option',
  'noscript', 'template', 'slot', 'portal', 'dialog',
  'foreignobject', 'animate', 'animatemotion', 'animatetransform', 'set', 'use',
  'audio', 'video', 'source', 'track', 'canvas', 'marquee',
])

const URL_ATTRIBUTES = new Set(['href', 'src', 'xlink:href', 'action', 'formaction', 'poster', 'background', 'cite', 'data'])
const BLOCKED_ATTRIBUTES = new Set(['srcdoc', 'srcset', 'ping', 'formaction', 'action'])

const SAFE_URL = /^(?:https?:|mailto:|tel:|#|\/(?!\/)|\.{0,2}\/|blob:|data:image\/(?:png|jpe?g|gif|webp);base64,)/i
const UNSAFE_STYLE = /expression\s*\(|url\s*\(|@import|behavior\s*:|-moz-binding/i

function isSafeUrl(value: string): boolean {
  // Control characters and whitespace are ignored by browsers when resolving a scheme.
  const compact = value.replace(/[\u0000- \u007f-\u009f]/g, '')
  if (compact === '') return true
  if (SAFE_URL.test(compact)) return true
  // Relative reference without a scheme (no colon before the first slash, ? or #).
  return !/^[a-z][a-z0-9+.-]*:/i.test(compact)
}

function scrubElement(element: Element) {
  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    const value = attribute.value

    if (name.startsWith('on') || BLOCKED_ATTRIBUTES.has(name)) {
      element.removeAttribute(attribute.name)
    } else if (URL_ATTRIBUTES.has(name) && !isSafeUrl(value)) {
      element.removeAttribute(attribute.name)
    } else if (name === 'style' && UNSAFE_STYLE.test(value)) {
      element.removeAttribute(attribute.name)
    }
  }

  if (element.tagName.toLowerCase() === 'a' && element.getAttribute('target') === '_blank') {
    element.setAttribute('rel', 'noopener noreferrer')
  }
}

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  // Fast path: nothing that could open a tag.
  if (!html.includes('<')) return html
  if (typeof DOMParser === 'undefined') {
    return html.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`)
  }

  const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html')
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_COMMENT)
  const toRemove: Node[] = []

  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.nodeType === Node.COMMENT_NODE) {
      toRemove.push(node)
    } else if (BLOCKED_TAGS.has((node as Element).tagName.toLowerCase())) {
      toRemove.push(node)
    } else {
      scrubElement(node as Element)
    }
  }

  for (const node of toRemove) {
    node.parentNode?.removeChild(node)
  }

  return doc.body.innerHTML
}
