/**
 * Search helpers shared by the source and result lists.
 * Matching ignores case, diacritics and apostrophes, like the server-side search:
 * "maverdi" finds "Mâverdî", "ibnul" finds "İbnü’l".
 */

const DROP = new Set(['’', "'", '`', '´', 'ʿ', 'ʾ', 'ʼ', '‘', 'ـ'])
const COMBINING = /[̀-ͯ҃-҉֑-ׇֽֿׁׂׅׄؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۤۧۨ-ۭ᪰-᫿᷀-᷿⃐-⃿︠-︯]/g

function foldChar(ch: string): string {
  if (DROP.has(ch)) return ''
  if (ch === 'ı') return 'i'
  if (ch === 'ß') return 'ss'
  return ch.normalize('NFKD').replace(COMBINING, '').toLowerCase()
}

export function foldText(text: string): string {
  let out = ''
  for (const ch of text || '') out += foldChar(ch)
  return out
}

/** Distinct query words, longest first. */
export function queryWords(query: string): string[] {
  const words = foldText(query).split(/\s+/).filter(Boolean)
  return Array.from(new Set(words)).sort((a, b) => b.length - a.length).slice(0, 8)
}

/** Every query word occurs in the text. */
export function matchesAll(text: string, words: string[]): boolean {
  if (!words.length) return true
  const folded = foldText(text)
  return words.every(w => folded.includes(w))
}

export interface TextSegment {
  text: string
  hit: boolean
}

function toSegments(text: string, ranges: Array<[number, number]>): TextSegment[] {
  if (!ranges.length) return [{ text, hit: false }]
  const sorted = [...ranges].sort((a, b) => a[0] - b[0])
  const merged: Array<[number, number]> = []
  for (const [s, e] of sorted) {
    const last = merged[merged.length - 1]
    if (last && s <= last[1]) last[1] = Math.max(last[1], e)
    else merged.push([s, e])
  }
  const segments: TextSegment[] = []
  let pos = 0
  for (const [s, e] of merged) {
    if (s > pos) segments.push({ text: text.slice(pos, s), hit: false })
    segments.push({ text: text.slice(s, e), hit: true })
    pos = e
  }
  if (pos < text.length) segments.push({ text: text.slice(pos), hit: false })
  return segments
}

/** Split text into plain and highlighted parts for the query words. */
export function highlight(text: string, words: string[]): TextSegment[] {
  if (!text || !words.length) return [{ text: text || '', hit: false }]
  // Folded text with the index of the source character for each folded character.
  const chars = Array.from(text)
  const offsets: number[] = []
  let folded = ''
  let offset = 0
  for (const ch of chars) {
    const f = foldChar(ch)
    for (let i = 0; i < f.length; i++) offsets.push(offset)
    folded += f
    offset += ch.length
  }
  const ranges: Array<[number, number]> = []
  for (const word of words) {
    let start = 0
    while (start <= folded.length) {
      const pos = folded.indexOf(word, start)
      if (pos < 0) break
      const begin = offsets[pos]!
      const lastIndex = offsets[pos + word.length - 1]!
      let end = lastIndex + (text.codePointAt(lastIndex)! > 0xffff ? 2 : 1)
      while (end < text.length && foldChar(text[end]!) === '' && !DROP.has(text[end]!)) end++
      ranges.push([begin, end])
      start = pos + word.length
    }
  }
  return toSegments(text, ranges)
}

/** Parts of a server snippet, using the match ranges it carries. */
export function snippetSegments(text: string, ranges: number[][]): TextSegment[] {
  return toSegments(text, ranges.map(r => [r[0]!, r[1]!] as [number, number]))
}
