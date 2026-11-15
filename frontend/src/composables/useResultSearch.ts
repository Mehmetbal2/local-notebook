/**
 * Search and filter state of the results list, shared by the three tabs of the
 * right panel, so the query and the chosen filter stay when the tab changes.
 */
import { effectScope, ref, watch } from 'vue'
import { searchProject, type SearchHit } from '@/services/api'
import { queryWords } from '@/utils/searchText'

/** all: everything · note: notes · tab: results of the current tab's tools · deep_research */
export type ResultKind = 'all' | 'note' | 'tab' | 'deep_research'

const projectId = ref('')
const query = ref('')
const searchContent = ref(false)
const kind = ref<ResultKind>('all')
const featureHits = ref<Map<string, SearchHit>>(new Map())
const workflowHits = ref<Map<string, SearchHit>>(new Map())
const searching = ref(false)

let started = false
let timer: ReturnType<typeof setTimeout> | null = null
let seq = 0

async function runSearch() {
  const text = query.value.trim()
  const current = ++seq
  if (!searchContent.value || text.length < 2 || !projectId.value || !queryWords(text).length) {
    featureHits.value = new Map()
    workflowHits.value = new Map()
    searching.value = false
    return
  }
  searching.value = true
  try {
    const data = await searchProject(projectId.value, text, 'features')
    if (current !== seq) return
    const toMap = (hits?: SearchHit[]) => new Map((hits || []).filter(h => h.count > 0).map(h => [h.id, h]))
    featureHits.value = toMap(data.features)
    workflowHits.value = toMap(data.workflows)
  } catch (error) {
    console.error('Result search failed:', error)
  } finally {
    if (current === seq) searching.value = false
  }
}

function start() {
  if (started) return
  started = true
  // Lives for the whole page, independent of which tab's list is mounted.
  effectScope(true).run(() => {
    watch([query, searchContent, projectId], () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(runSearch, 350)
    })
  })
}

export function useResultSearch(currentProjectId: string) {
  start()
  if (projectId.value !== currentProjectId) {
    // Another project: start with an empty search.
    projectId.value = currentProjectId
    query.value = ''
    kind.value = 'all'
    featureHits.value = new Map()
    workflowHits.value = new Map()
  }
  function clear() {
    query.value = ''
    kind.value = 'all'
  }
  return { query, searchContent, kind, featureHits, workflowHits, searching, clear }
}
