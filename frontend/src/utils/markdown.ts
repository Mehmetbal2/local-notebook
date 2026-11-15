

import { marked } from 'marked'
import katex from 'katex'
import { escapeHtml } from './format'
import { sanitizeHtml } from './sanitize'


marked.setOptions({
  breaks: true,
  gfm: true
})

/**
 * Upright Greek letters from the LaTeX `upgreek` package (`\\upeta`, `\\Upgamma`…).
 * OCR output uses them and KaTeX does not know them, so they would show up as
 * red command names; the ordinary letter is the closest KaTeX has.
 */
const UPGREEK_LETTERS = [
  'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota',
  'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma', 'tau', 'upsilon',
  'phi', 'chi', 'psi', 'omega', 'varepsilon', 'vartheta', 'varpi', 'varrho',
  'varsigma', 'varphi',
]
const UPGREEK_CAPITALS = ['Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma', 'Upsilon', 'Phi', 'Psi', 'Omega']
const KATEX_MACROS: Record<string, string> = Object.fromEntries([
  ...UPGREEK_LETTERS.map((name) => [`\\up${name}`, `\\${name}`]),
  ...UPGREEK_CAPITALS.map((name) => [`\\Up${name.toLowerCase()}`, `\\${name}`]),
])

/** KaTeX may add to the macro table it is given, so every call gets a copy. */
function katexOptions(displayMode: boolean) {
  return { displayMode, throwOnError: false, macros: { ...KATEX_MACROS } }
}

type ProtectedItem = {
  placeholder: string
  content: string
}

function protectItem(
  protectedItems: ProtectedItem[],
  content: string,
  prefix = 'HTML'
): string {
  const placeholder = `%%${prefix}_${protectedItems.length}%%`
  protectedItems.push({ placeholder, content })
  return placeholder
}

function renderLatex(latex: string, displayMode: boolean, fallback: string): string {
  try {
    return katex.renderToString(latex.trim(), katexOptions(displayMode))
  } catch {
    return escapeHtml(fallback)
  }
}

function protectLatex(text: string, protectedItems: ProtectedItem[]): string {
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (_, latex) => {
    return protectItem(
      protectedItems,
      renderLatex(latex, true, `$$${latex}$$`),
      'LATEX_BLOCK'
    )
  })

  return text.replace(/(^|[^\\$])\$([^\s\d$\n](?:[^$\n]*?[^\s$])?)\$(?!\$)/g, (_, prefix, latex) => {
    return prefix + protectItem(
      protectedItems,
      renderLatex(latex, false, `$${latex}$`),
      'LATEX_INLINE'
    )
  })
}

function restoreProtectedItems(html: string, protectedItems: ProtectedItem[]): string {
  for (const { placeholder, content } of protectedItems) {
    html = html.split(placeholder).join(content)
  }
  return html
}


export function renderMarkdownWithLatex(text: string): string {

  const protectedItems: ProtectedItem[] = []


  text = text.replace(/<span\s+class="inline-citation[^"]*"[^>]*>[\s\S]*?<\/span>/g, (match) => {
    return protectItem(protectedItems, match, 'CITATION')
  })

  text = protectLatex(text, protectedItems)

  const html = marked(text) as string

  return sanitizeHtml(restoreProtectedItems(html, protectedItems))
}

/** Reverses escapeHtml for a formula, so KaTeX sees `<`, `>` and `&` as written. */
function unescapeLatex(latex: string): string {
  return latex
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
}

/** Stands in for an escaped dollar sign (`\\$`) while formulas are located. */
const ESCAPED_DOLLAR = '\uE000'

/**
 * Renders the formulas in plain source text (OCR output); everything else is
 * shown as written.
 *
 * - `\\$` is a literal dollar sign, never a delimiter.
 * - An inline formula starts and ends with a non-space character, as in Pandoc.
 *   OCR text often holds an unpaired `$` (a formula cut at a block boundary);
 *   without this rule the pairing shifts by one and the gaps between formulas
 *   are rendered instead of the formulas.
 * - A closing `$` is not followed by a digit, so "$5-$10" stays text.
 * - OCR sometimes writes the closing delimiter as `\\$`; an open formula that
 *   runs into `\\$` followed by a space or the end of the text is closed there.
 */
export function renderLatexOnly(text: string): string {
  if (!text) return ''

  const rendered: ProtectedItem[] = []
  const toLatex = (latex: string) =>
    unescapeLatex(latex).split(ESCAPED_DOLLAR).join('\\$').trim()
  const render = (latex: string, displayMode: boolean, fallback: string) => {
    let output: string
    try {
      output = katex.renderToString(toLatex(latex), katexOptions(displayMode))
    } catch {
      output = fallback
    }
    return protectItem(rendered, output, displayMode ? 'LATEX_BLOCK' : 'LATEX_INLINE')
  }

  // The text is escaped first; formulas are unescaped again before rendering
  // (KaTeX escapes its own output), the rest stays escaped.
  let html = escapeHtml(text).replace(/\\\$/g, ESCAPED_DOLLAR)

  html = html.replace(/\$\$([^$]+)\$\$/g, (match, latex) => render(latex, true, match))
  html = html.replace(
    /\$([^\s$\uE000](?:[^$\n]*?[^\s$\uE000])?)(?:\$(?!\d)|\uE000(?=\s|$))/g,
    (match, latex) => render(latex, false, match)
  )

  return restoreProtectedItems(html, rendered).split(ESCAPED_DOLLAR).join('$')
}

export function renderSummary(summary: string): string {
  if (!summary) return ''
  return renderMarkdownWithLatex(summary)
}

export function parseInlineMarkdown(text: string): string {
  if (!text) return ''

  const protectedItems: ProtectedItem[] = []

  let processedText = text
    .replace(/\\n/g, '\n')

  processedText = protectLatex(processedText, protectedItems)

  processedText = processedText.replace(
    /\[citation_(\d+)\]/g,
    '<sup class="inline-citation">$1</sup>'
  )

  processedText = processedText.replace(
    /\[citation:[^\]]+\]/g,
    '<span class="inline-citation segment-citation disabled unresolved" data-citation-type="segment"></span>'
  )

  processedText = processedText.replace(
    /#([\u4e00-\u9fa5a-zA-Z0-9_]+)/g,
    '<span class="hashtag">#$1</span>'
  )

  let html = marked.parseInline(processedText) as string

  html = html.replace(/\n/g, '<br>')

  return sanitizeHtml(restoreProtectedItems(html, protectedItems))
}
