/**
 * Turns the flat block list of a quick-tool result into the structures the
 * interactive views need (cards, quiz questions, timeline entries, mind-map tree),
 * and back into Markdown for copy / download.
 *
 * Every parser returns null when the blocks do not follow the expected layout,
 * so older or free-form results simply fall back to the document view.
 */
import type { Feature, FeatureBlock, FeatureContentPart, FeatureTextBlock } from '../../../types'

export type Parts = FeatureContentPart[]

export interface CardItem {
  group: string
  front: Parts
  back: FeatureTextBlock[]
}

export interface QuizOption {
  letter: string
  parts: Parts
}

export interface QuizQuestion {
  group: string
  prompt: Parts
  options: QuizOption[]
  /** Letter of the correct option; null for short-answer questions. */
  correct: string | null
  explanation: Parts
}

export interface TimelineEntry {
  group: string
  label: string
  title: Parts
  body: FeatureTextBlock[]
}

export interface MindNode {
  id: string
  parts: Parts
  children: MindNode[]
}

export type InteractiveKind = 'flashcards' | 'faq' | 'quiz' | 'timeline' | 'mind_map' | 'podcast'

export interface DialogueTurn {
  speaker: 'HOST' | 'GUEST'
  parts: Parts
}

const TEXT_BLOCK_TYPES = new Set(['heading', 'paragraph', 'list', 'quote'])

function isTextBlock(block: FeatureBlock): block is FeatureTextBlock {
  return TEXT_BLOCK_TYPES.has(block.block_type)
}

export function partsToText(parts: Parts | undefined): string {
  return (parts || [])
    .map((part) => (part.type === 'text' ? part.content || '' : ''))
    .join('')
    .trim()
}

function stripInlineMarkdown(text: string): string {
  return text.replace(/[*_`]+/g, '').trim()
}

/** Removes `pattern` from the start of the first text part, leaving citations in place. */
function trimLeading(parts: Parts, pattern: RegExp): Parts {
  let done = false
  return parts.map((part) => {
    if (done || part.type !== 'text') return part
    done = true
    return { ...part, content: (part.content || '').replace(pattern, '') }
  })
}

interface Section {
  group: string
  heading: FeatureTextBlock
  body: FeatureTextBlock[]
}

/** Splits blocks into items led by a heading of the "item" level, tracking the group heading above. */
function splitSections(blocks: FeatureBlock[]): Section[] {
  const textBlocks = blocks.filter(isTextBlock)
  const count = (level: number) =>
    textBlocks.filter((block) => block.block_type === 'heading' && (block.level || 2) === level).length

  // Items are `###` headings; `####` is accepted when a model nests one level deeper.
  let itemLevel = 3
  if (count(3) < 2) {
    if (count(4) >= 2) itemLevel = 4
    else return []
  }

  const sections: Section[] = []
  let group = ''
  let current: Section | null = null

  for (const block of textBlocks) {
    if (block.block_type === 'heading') {
      const level = block.level || 2
      if (level === itemLevel) {
        current = { group, heading: block, body: [] }
        sections.push(current)
        continue
      }
      if (level < itemLevel) {
        group = stripInlineMarkdown(partsToText(block.content_parts))
        current = null
        continue
      }
    }
    if (current) current.body.push(block)
  }

  return sections
}

const BOLD_LEAD = /^\s*\*\*([^*]+?)\*\*[\s:：—–-]*/
const CARD_NUMBER_PREFIX = /^[^\d\n]{0,14}\d+\s*[—–\-:：.)]\s*/

/** Older results wrote each card as one paragraph: `**Card 3 — question?** answer`. */
function parseBoldLeadCards(blocks: FeatureBlock[]): CardItem[] {
  const cards: CardItem[] = []
  let group = ''

  for (const block of blocks) {
    if (!isTextBlock(block)) continue
    if (block.block_type === 'heading') {
      group = stripInlineMarkdown(partsToText(block.content_parts))
      continue
    }
    if (block.block_type !== 'paragraph' || block.extra?.is_table) continue

    const first = block.content_parts[0]
    if (!first || first.type !== 'text') continue
    const match = BOLD_LEAD.exec(first.content || '')
    if (!match) continue

    const question = match[1]!.replace(CARD_NUMBER_PREFIX, '').trim()
    const answer = trimLeading(block.content_parts, BOLD_LEAD)
    if (!question || !partsToText(answer)) continue

    cards.push({
      group,
      front: [{ type: 'text', content: question }],
      back: [{ block_type: 'paragraph', content_parts: answer }],
    })
  }

  return cards
}

export function parseCards(blocks: FeatureBlock[]): CardItem[] | null {
  let cards: CardItem[] = splitSections(blocks)
    .filter((section) => section.body.length > 0)
    .map((section) => ({
      group: section.group,
      front: trimLeading(section.heading.content_parts, /^\s*(?:\d+[.)]\s*)/),
      back: section.body,
    }))
  if (cards.length < 3) cards = parseBoldLeadCards(blocks)
  return cards.length >= 3 ? cards : null
}

const OPTION_LABEL = /^\s*\(?([A-Ha-h])[).:]\s+/
const ANSWER_MARK = /^\s*(?:✓|✔|☑|✅)\s*/
const ANSWER_LETTER = /^\s*(?:✓|✔|☑|✅)\s*\(?([A-Ha-h])\)?(?=\s*(?:[—–\-:.)]|$))\s*[—–\-:.)]*\s*/

export function parseQuiz(blocks: FeatureBlock[]): QuizQuestion[] | null {
  const questions: QuizQuestion[] = []

  for (const section of splitSections(blocks)) {
    const optionBlocks = section.body.filter((block) => block.block_type === 'list')
    const answerBlock = section.body.find(
      (block) =>
        (block.block_type === 'quote' || block.block_type === 'paragraph') &&
        ANSWER_MARK.test(partsToText(block.content_parts)),
    )
    if (!answerBlock) continue

    const options: QuizOption[] = []
    for (const block of optionBlocks) {
      const match = OPTION_LABEL.exec(partsToText(block.content_parts))
      if (!match) continue
      options.push({
        letter: match[1]!.toUpperCase(),
        parts: trimLeading(block.content_parts, OPTION_LABEL),
      })
    }

    const answerText = partsToText(answerBlock.content_parts)
    const letterMatch = options.length >= 2 ? ANSWER_LETTER.exec(answerText) : null
    const correct = letterMatch ? letterMatch[1]!.toUpperCase() : null
    const hasCorrectOption = correct !== null && options.some((option) => option.letter === correct)

    questions.push({
      group: section.group,
      prompt: trimLeading(section.heading.content_parts, /^\s*(?:\d+[.)]\s*)/),
      options: hasCorrectOption ? options : [],
      correct: hasCorrectOption ? correct : null,
      explanation: trimLeading(answerBlock.content_parts, hasCorrectOption ? ANSWER_LETTER : ANSWER_MARK),
    })
  }

  return questions.length >= 2 ? questions : null
}

const TIMELINE_SEPARATOR = /\s+\|\s+/

export function parseTimeline(blocks: FeatureBlock[]): TimelineEntry[] | null {
  const entries: TimelineEntry[] = []

  for (const section of splitSections(blocks)) {
    const headingText = partsToText(section.heading.content_parts)
    const match = TIMELINE_SEPARATOR.exec(headingText)
    if (!match) continue
    const label = stripInlineMarkdown(headingText.slice(0, match.index))
    const leading = new RegExp(`^[\\s\\S]{${match.index + match[0].length}}`)
    entries.push({
      group: section.group,
      label,
      title: trimLeading(section.heading.content_parts, leading),
      body: section.body,
    })
  }

  return entries.length >= 3 ? entries : null
}

export function parseMindMap(blocks: FeatureBlock[], fallbackTitle: string): MindNode | null {
  const textBlocks = blocks.filter(isTextBlock)
  const headings = textBlocks.filter((block) => block.block_type === 'heading')
  if (headings.length < 2) return null

  const minLevel = Math.min(...headings.map((block) => block.level || 2))
  const topCount = headings.filter((block) => (block.level || 2) === minLevel).length

  let nextId = 0
  const makeNode = (parts: Parts): MindNode => ({ id: `n${nextId++}`, parts, children: [] })

  // A single top heading is the centre; otherwise the result title is.
  const root = makeNode([{ type: 'text', content: fallbackTitle }])
  const rootDepth = topCount === 1 ? minLevel : minLevel - 1
  const stack: Array<{ depth: number; node: MindNode }> = [{ depth: rootDepth, node: root }]
  let headingDepth = rootDepth
  let nodeCount = 0

  for (const block of textBlocks) {
    let depth: number
    if (block.block_type === 'heading') {
      depth = block.level || 2
      if (depth === rootDepth && topCount === 1) {
        root.parts = block.content_parts
        continue
      }
      headingDepth = depth
    } else if (block.block_type === 'list') {
      depth = headingDepth + 1 + (block.extra?.indent || 0)
    } else {
      continue
    }

    while (stack.length > 1 && stack[stack.length - 1]!.depth >= depth) stack.pop()
    const node = makeNode(block.content_parts)
    stack[stack.length - 1]!.node.children.push(node)
    stack.push({ depth, node })
    nodeCount += 1
  }

  return nodeCount >= 4 && root.children.length >= 2 ? root : null
}

export function getInteractiveKind(feature: Pick<Feature, 'feature_type'>): InteractiveKind | null {
  switch (feature.feature_type) {
    case 'flashcards':
    case 'faq':
    case 'quiz':
    case 'timeline':
    case 'mind_map':
    case 'podcast':
      return feature.feature_type
    default:
      return null
  }
}

const SPEAKER_TAG = /^\s*(?:\*\*|__)?\s*(HOST|GUEST)\s*[:：]\s*(?:\*\*|__)?\s*/i

/** Dialogue turns of a podcast script: one paragraph per `HOST:` / `GUEST:` line. */
export function parseDialogue(blocks: FeatureBlock[]): DialogueTurn[] | null {
  const turns: DialogueTurn[] = []
  for (const block of blocks) {
    if (!isTextBlock(block) || block.block_type === 'heading') continue
    const text = partsToText(block.content_parts)
    const match = SPEAKER_TAG.exec(text)
    if (match) {
      turns.push({
        speaker: match[1]!.toUpperCase() as DialogueTurn['speaker'],
        parts: trimLeading(block.content_parts, SPEAKER_TAG),
      })
    } else if (turns.length > 0) {
      turns[turns.length - 1]!.parts = [...turns[turns.length - 1]!.parts, { type: 'text', content: ' ' }, ...block.content_parts]
    }
  }
  return turns.length >= 4 ? turns : null
}

/** Strips speaker tags for the copy / download text of a podcast script. */
export function speakerLabelFor(speaker: DialogueTurn['speaker'], labels: { host: string; guest: string }): string {
  return speaker === 'HOST' ? labels.host : labels.guest
}

// ---------- Markdown export ----------

const RULE_TEXT = /^\s*([-*_])(\s*\1){2,}\s*$/

/** A paragraph that is only a markdown horizontal rule ("---"), which the backend keeps as text. */
export function isRuleBlock(block: FeatureBlock): boolean {
  if (!isTextBlock(block) || block.block_type !== 'paragraph') return false
  const parts = block.content_parts || []
  return parts.length > 0 && parts.every((part) => part.type === 'text') && RULE_TEXT.test(parts.map((part) => part.content || '').join(''))
}

function partsToMarkdown(parts: Parts | undefined): string {
  return (parts || [])
    .map((part) => (part.type === 'text' ? part.content || '' : `[${part.display_num}]`))
    .join('')
}

/** "Title, Source (Year). URL" for a web citation; null for other kinds. */
function webReference(record: Record<string, unknown>): string | null {
  const url = String(record.url || '').trim()
  if (!url || record.file_name) return null
  const title = String(record.title || '').trim()
  const source = String(record.source || '').trim()
  const year = String(record.published_date || '').trim().slice(0, 4)
  const head = [title, source].filter(Boolean).join(', ')
  return `${head}${year ? ` (${year})` : ''}${head ? '. ' : ''}${url}`
}

export function blocksToMarkdown(
  feature: Pick<Feature, 'title' | 'blocks' | 'citations'>,
  speakerLabels?: { host: string; guest: string },
  formatReference?: (citationId: string) => string | null,
): string {
  const lines: string[] = []
  const blocks = feature.blocks || []
  const title = (feature.title || '').trim()

  // The document title is the only H1. The content's own headings keep their relative
  // levels but start at H2, so they never sit beside or above the title in the outline.
  const headingLevels = blocks
    .filter((block) => isTextBlock(block) && block.block_type === 'heading')
    .map((block) => (block as FeatureTextBlock).level || 2)
  const levelOffset = headingLevels.length > 0 ? 2 - Math.min(...headingLevels) : 0
  const firstBlock = blocks[0]
  const firstHeadingRepeatsTitle =
    !!title &&
    !!firstBlock &&
    isTextBlock(firstBlock) &&
    firstBlock.block_type === 'heading' &&
    partsToMarkdown(firstBlock.content_parts).trim().toLowerCase() === title.toLowerCase()
  if (title) lines.push(`# ${title}`, '')

  let previousType = ''
  for (const [index, block] of blocks.entries()) {
    if (!isTextBlock(block)) continue
    if (index === 0 && firstHeadingRepeatsTitle) continue
    if (block.block_type !== 'list' && previousType === 'list') lines.push('')

    if (block.block_type === 'heading') {
      const level = Math.min(Math.max((block.level || 2) + levelOffset, 2), 6)
      lines.push(`${'#'.repeat(level)} ${partsToMarkdown(block.content_parts)}`, '')
    } else if (block.block_type === 'list') {
      lines.push(`${'  '.repeat(block.extra?.indent || 0)}- ${partsToMarkdown(block.content_parts)}`)
    } else if (block.block_type === 'quote') {
      lines.push(`> ${partsToMarkdown(block.content_parts)}`, '')
    } else if (block.extra?.is_table && block.content) {
      lines.push(block.content.replace(/\[citation_[a-zA-Z0-9_]+\]/g, (token) => {
        const num = feature.citations?.[token.slice(1, -1)]?.display_num
        return num ? `[${num}]` : ''
      }), '')
    } else if (isRuleBlock(block)) {
      lines.push('---', '')
    } else {
      let text = partsToMarkdown(block.content_parts)
      if (speakerLabels) {
        text = text.replace(SPEAKER_TAG, (_, tag: string) => `**${speakerLabelFor(tag.toUpperCase() as DialogueTurn['speaker'], speakerLabels)}:** `)
      }
      lines.push(text, '')
    }
    previousType = block.block_type
  }

  const sources = Object.entries(feature.citations || {})
    .filter(([, citation]) => typeof citation.display_num === 'number')
    .sort(([, a], [, b]) => (a.display_num || 0) - (b.display_num || 0))
  if (sources.length > 0) {
    if (lines[lines.length - 1] !== '') lines.push('')
    lines.push('---', '')
    const seen = new Set<number>()
    for (const [citationId, citation] of sources) {
      const num = citation.display_num as number
      if (seen.has(num)) continue
      seen.add(num)
      const record = citation as unknown as Record<string, unknown>
      const entry = formatReference?.(citationId) || webReference(record) || String(record.file_name || record.title || record.url || '').trim()
      // Separate lines in Markdown need a blank line between them.
      lines.push(`[${num}] ${entry}`.trimEnd(), '')
    }
  }

  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n'
}
