import axios from 'axios'
import type { Project, FileInfo, Session, ToolExecuting, FileContent, Feature, FeatureBlock, ImageFileInfo } from '../types'
import { getToken, clearTokens, getMediaToken, setMediaToken, mediaTokenNeedsRefresh } from './auth'
import { getModelOutputLanguage, t } from '../i18n'
import { UI_LANGUAGE_HEADER, currentUiLanguage } from './uiLanguageHeader'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})


api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers[UI_LANGUAGE_HEADER] = currentUiLanguage()
  return config
})


let lastToastTime = 0
const TOAST_DEBOUNCE = 3000

function showGlobalToast(message: string) {
  const now = Date.now()
  if (now - lastToastTime < TOAST_DEBOUNCE) return
  lastToastTime = now


  window.dispatchEvent(new CustomEvent('global-toast', {
    detail: { message, type: 'warning' }
  }))
}


function is429Error(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const err = error as { response?: { status?: number }; status?: number }
  return err.response?.status === 429 || err.status === 429
}


let isRedirectingToLogin = false


api.interceptors.response.use(
  (response) => response,
  async (error) => {

    if (is429Error(error)) {
      showGlobalToast(t('ui.tooManyRequestsTryAgainLater'))
      return Promise.reject(error)
    }

    if (error.response?.status === 401) {

      const url = error.config?.url || ''
      if (url.includes('/auth/login')) {
        return Promise.reject(error)
      }


      if (isRedirectingToLogin) {
        return new Promise(() => {})
      }

      isRedirectingToLogin = true
      clearTokens()

      setTimeout(() => { isRedirectingToLogin = false }, 3000)
      window.location.href = '/login'
      return new Promise(() => {})
    }

    return Promise.reject(error)
  }
)


export async function login(username: string, password: string) {


  const form = new URLSearchParams({ username, password })
  const response = await axios.post(`${API_BASE}/api/auth/login`, form)
  return response.data
}

/** Fetch a fresh short-lived media token (for preview URLs) when it is missing or about to expire. */
export async function refreshMediaToken(marginMs = 2 * 60 * 60 * 1000): Promise<void> {
  if (!getToken() || !mediaTokenNeedsRefresh(marginMs)) return
  try {
    const response = await api.get('/api/auth/media-token')
    if (response.data?.media_token) {
      setMediaToken(response.data.media_token, Number(response.data.expires_in) || 0)
    }
  } catch {
    // Signed out or offline: previews fail until the next successful refresh.
  }
}

let mediaTokenTimer: ReturnType<typeof setInterval> | null = null

export function startMediaTokenRefresh() {
  if (mediaTokenTimer) return
  mediaTokenTimer = setInterval(() => { void refreshMediaToken() }, 15 * 60 * 1000)
}

export async function getCurrentUser() {
  const response = await api.get('/api/auth/me')
  return response.data
}

export type AdminUserRole = 'user' | 'admin'

export interface AdminUser {
  user_id: string
  username: string
  role: AdminUserRole
  created_at: string
  updated_at: string
}

export interface AdminUserListResponse {
  users: AdminUser[]
  total: number
}

export async function getAdminUsers(): Promise<AdminUserListResponse> {
  const response = await api.get('/api/admin/users')
  return response.data
}

export interface AdminUserStatsRow {
  user_id: string | null
  username: string
  role: AdminUserRole | 'unassigned'
  projects: number
  files: number
  ready_files: number
  storage_bytes: number
  sessions: number
  messages: number
  outputs: number
  llm_calls: number
  tokens: number
  last_active_at: string | null
}

export interface AdminUserStatsResponse {
  period_days: number
  rows: AdminUserStatsRow[]
  totals: Omit<AdminUserStatsRow, 'user_id' | 'username' | 'role' | 'last_active_at'> & {
    active_users: number
  }
}

/** Per-user content (all time) and LLM usage for the last `days` days. */
export async function getAdminUserStats(days = 30): Promise<AdminUserStatsResponse> {
  const response = await api.get('/api/admin/users/stats', { params: { days } })
  return response.data
}

export async function createAdminUser(data: {
  username: string
  password: string
}): Promise<AdminUser> {
  const response = await api.post('/api/admin/users', data)
  return response.data
}

export async function resetAdminUserPassword(userId: string, newPassword: string): Promise<void> {
  await api.post(`/api/admin/users/${userId}/password`, { new_password: newPassword })
}

export interface AdminUsageRow {
  usage_date: string
  user_id: string
  username: string
  model: string
  call_count: number
  input_uncached_tokens: number
  input_cache_read_tokens: number
  input_cache_write_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface AdminUsageTotals {
  call_count: number
  input_uncached_tokens: number
  input_cache_read_tokens: number
  input_cache_write_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface AdminUsageResponse {
  rows: AdminUsageRow[]
  totals: AdminUsageTotals
}

export async function getAdminUsage(params?: {
  start_date?: string
  end_date?: string
  user_id?: string
}): Promise<AdminUsageResponse> {
  const response = await api.get('/api/admin/usage', { params })
  return response.data
}

export interface AdminDiagnosticsCollection {
  exists: boolean
  rows: number
  dim: number | null
}

export interface AdminDiagnostics {
  app: {
    version: string
    python: string
    platform: string
    uptime_seconds: number | null
  }
  database: {
    path: string | null
    size_bytes: number | null
    counts: Record<string, number>
  }
  vectors: {
    mode?: string
    error?: string
    file_size_bytes: number | null
    collections: Record<string, AdminDiagnosticsCollection>
  }
  storage: {
    data_dir: string
    data_bytes: number
    uploads_bytes: number
    disk_free_bytes: number
    disk_total_bytes: number
  }
  services: {
    searxng: { url?: string; reachable: boolean; error?: string }
    embedding: {
      source: string
      url?: string
      model?: string
      dim?: number | null
      device?: string
      local_running: boolean
      local_port?: number | null
      error?: string
    }
    llm: { configured: boolean; model: string; api_format: string }
  }
  logs: { recent: string[] }
}

export async function getAdminDiagnostics(): Promise<AdminDiagnostics> {
  const response = await api.get('/api/admin/diagnostics')
  return response.data
}

export interface PreparedBackup {
  download_url: string
  filename: string
  size_bytes: number
  expires_in: number
}

/**
 * Build a backup zip (database + local vectors, optionally uploaded sources) on the server.
 * The result is a one-time link: open it as a normal download so the browser streams the
 * archive to disk instead of holding it in memory.
 */
export async function prepareAdminBackup(
  includeUploads: boolean,
  includeVectors = true,
): Promise<PreparedBackup> {
  const response = await api.post('/api/admin/backup/prepare', null, {
    params: { include_uploads: includeUploads, include_vectors: includeVectors },
    timeout: 600000,
  })
  const { download_path, ...rest } = response.data
  return { ...rest, download_url: `${API_BASE}${download_path}` }
}

/** Stage a backup for restore; it is applied on the next application start. */
export async function stageAdminRestore(
  file: File,
): Promise<{ ok: boolean; message: string; manifest?: Record<string, unknown> }> {
  const form = new FormData()
  form.append('file', file)
  // Axios turns FormData into JSON when the instance default is application/json;
  // the multipart header makes it pass the FormData through (as the upload calls do).
  const response = await api.post('/api/admin/restore', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
  })
  return response.data
}


export async function getProjects(): Promise<Project[]> {
  const response = await api.get('/api/projects')
  return response.data
}

export async function getProject(projectId: string): Promise<Project & { files: FileInfo[] }> {
  const response = await api.get(`/api/projects/${projectId}`)
  return response.data
}

export async function createProject(name: string, description: string = ''): Promise<Project> {
  const response = await api.post('/api/projects', { name, description })
  return response.data
}

export async function deleteProject(projectId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}`)
}

export async function updateProject(projectId: string, data: { name?: string; description?: string }): Promise<Project> {
  const response = await api.patch(`/api/projects/${projectId}`, data)
  return response.data
}


export async function getFiles(projectId: string): Promise<FileInfo[]> {
  const response = await api.get(`/api/projects/${projectId}/files`)
  return response.data
}


export type UploadProgressCallback = (progress: number) => void

export async function uploadFile(
  projectId: string,
  file: File,
  onProgress?: UploadProgressCallback,
  outputLanguage?: string
): Promise<FileInfo> {
  const formData = new FormData()
  formData.append('file', file)
  if (outputLanguage) {
    formData.append('output_language', outputLanguage)
  }

  const response = await api.post(`/api/projects/${projectId}/files`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000,
    onUploadProgress: onProgress ? (progressEvent) => {
      if (progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    } : undefined
  })
  return response.data
}

export async function getFile(fileId: string): Promise<FileInfo> {
  const response = await api.get(`/api/files/${fileId}`)
  return response.data
}

export async function getFileContent(fileId: string): Promise<FileContent> {

  const response = await api.get(`/api/files/${fileId}/content`, { timeout: 60000 })
  return response.data
}


export interface PageInfoItem {
  page: number
  block_count: number
}

export interface FilePageInfo {
  file_id: string
  file_name: string
  file_type: string
  has_pages: boolean
  total_pages: number
  pages: PageInfoItem[]
  segments: Array<{
    segment_id: string
    block_ids: string[]
    summary: string
  }>

  blocks?: Array<{
    block_id: string
    page: number
    extra?: {
      is_image?: boolean
      image_index?: number
      image_name?: string
      bbox?: number[]
    }
  }>
}


export interface PageContentBlock {
  block_id: string
  block_type: 'heading' | 'paragraph' | 'list' | 'quote'
  content: string
  page: number
}

export interface FilePageContent {
  file_id: string
  file_name: string
  page: number
  end_page: number
  blocks: PageContentBlock[]
}


export interface BlockLocation {
  page: number
  block_index: number
  exists: boolean
}

export interface BlocksLocationResponse {
  file_id: string
  blocks: Record<string, BlockLocation>
}


export async function getFilePageInfo(fileId: string): Promise<FilePageInfo> {
  const response = await api.get(`/api/files/${fileId}/content/pages`)
  return response.data
}


export async function getFilePage(fileId: string, pageNum: number, range?: string): Promise<FilePageContent> {
  const url = range
    ? `/api/files/${fileId}/content/page/${pageNum}?range=${range}`
    : `/api/files/${fileId}/content/page/${pageNum}`
  const response = await api.get(url)
  return response.data
}


export async function getFilePageRange(fileId: string, startPage: number, endPage: number): Promise<FilePageContent> {
  const response = await api.get(`/api/files/${fileId}/content/page/${startPage}?range=${startPage}-${endPage}`)
  return response.data
}


export async function getBlocksLocation(fileId: string, blockIds: string[]): Promise<BlocksLocationResponse> {
  const response = await api.post(`/api/files/${fileId}/blocks/location`, { block_ids: blockIds })
  return response.data
}

export async function deleteFile(fileId: string): Promise<void> {
  await api.delete(`/api/files/${fileId}`)
}

/** Stop parsing the given files; returns the ids that were actually pending or processing. */
export async function cancelFilesProcessing(fileIds: string[]): Promise<{ stopped: string[] }> {
  const response = await api.post('/api/files/cancel/batch', { file_ids: fileIds })
  return response.data
}

/** Delete several files at once; running parses are stopped first. */
export async function deleteFilesBatch(fileIds: string[]): Promise<{ deleted: string[] }> {
  const response = await api.post('/api/files/delete/batch', { file_ids: fileIds }, { timeout: 120000 })
  return response.data
}

export interface FileNameSuggestion {
  id: string
  file_name: string
  author: string
  year: string
  title: string
  confidence: 'high' | 'medium' | 'low'
  note: string
}

/** Ask the model for an "Author - Year - Title" name; nothing is renamed until the user confirms. */
export async function suggestFileName(fileId: string, outputLanguage?: string): Promise<FileNameSuggestion> {
  const response = await api.post(`/api/files/${fileId}/name-suggestion`, { output_language: outputLanguage }, { timeout: 180000 })
  return response.data
}

export interface WebSourceResult {
  url: string
  title: string
  snippet: string
  domain: string
  published_date: string
  engines: string[]
  kind: 'pdf' | 'page'
  reason: string
  imported: boolean
  /** full: a PDF can be downloaded; oa_page: a free page; abstract: only the publisher page; page: web page */
  access?: 'full' | 'oa_page' | 'abstract' | 'page'
  doi?: string
  pdf_url?: string
  landing_url?: string
  authors?: string[]
  venue?: string
}

export interface WebSourceImportItem {
  url: string
  title?: string
  pdf_url?: string
  landing_url?: string
  doi?: string
  authors?: string[]
  published_date?: string
}

export interface WebSourceSearchResponse {
  scope: 'web' | 'academic'
  queries: string[]
  results: WebSourceResult[]
}

export interface WebSourceImportResponse {
  imported: FileInfo[]
  failed: { url: string; title: string; reason: string }[]
  skipped: { url: string; title: string }[]
  abstract_only?: string[]
}

/** Phase 1: search the user's own wording only. Results appear without waiting for the model. */
export async function searchWebSources(
  projectId: string,
  query: string,
  scope: 'web' | 'academic',
  outputLanguage?: string
): Promise<WebSourceSearchResponse> {
  const response = await api.post(
    `/api/projects/${projectId}/web-sources/search`,
    { query, scope, output_language: outputLanguage },
    { timeout: 60000 }
  )
  return response.data
}

/** Phase 2: let the model write extra queries and search them for additional sources. */
export async function expandWebSources(
  projectId: string,
  query: string,
  scope: 'web' | 'academic',
  excludeUrls: string[],
  outputLanguage?: string
): Promise<WebSourceSearchResponse> {
  const response = await api.post(
    `/api/projects/${projectId}/web-sources/search/expand`,
    {
      query,
      scope,
      output_language: outputLanguage,
      exclude_urls: excludeUrls,
    },
    { timeout: 120000 }
  )
  return response.data
}

export interface SearchSnippet {
  text: string
  ranges: number[][]
  page?: number
  /** Report section the passage comes from (report matches only) */
  section?: string
}

export interface SearchHit {
  id: string
  name_match: boolean
  count: number
  snippets: SearchSnippet[]
}

/** Search inside the project's source texts and/or its notes and results. */
export async function searchProject(
  projectId: string,
  query: string,
  target: 'all' | 'files' | 'features' = 'all'
): Promise<{ query: string; files?: SearchHit[]; features?: SearchHit[]; workflows?: SearchHit[] }> {
  const response = await api.get(`/api/projects/${projectId}/search`, { params: { q: query, target } })
  return response.data
}

/** Start a background deep research; its cited report appears among the project's results. */
export async function startDeepResearch(
  projectId: string,
  query: string,
  scope: 'web' | 'academic',
  outputLanguage?: string
): Promise<FeatureListItem> {
  const response = await api.post(`/api/projects/${projectId}/web-sources/deep-research`, {
    query,
    scope,
    output_language: outputLanguage,
  })
  return response.data
}

/** Second step of a search: the model orders the shown results and explains each one. */
export async function rankWebSources(
  projectId: string,
  query: string,
  scope: 'web' | 'academic',
  items: WebSourceResult[],
  outputLanguage?: string
): Promise<{ ok: boolean; order: { url: string; reason: string }[] }> {
  const response = await api.post(
    `/api/projects/${projectId}/web-sources/rank`,
    {
      query,
      scope,
      output_language: outputLanguage,
      items: items.map(r => ({
        url: r.url,
        title: r.title,
        snippet: r.snippet,
        venue: r.venue,
        domain: r.domain,
        published_date: r.published_date,
      })),
    },
    { timeout: 300000 }
  )
  return response.data
}

/** Download the chosen links (PDF or page text) and add them as sources. */
export async function importWebSources(
  projectId: string,
  items: WebSourceImportItem[],
  outputLanguage?: string
): Promise<WebSourceImportResponse> {
  const response = await api.post(
    `/api/projects/${projectId}/web-sources/import`,
    { items, output_language: outputLanguage },
    { timeout: 300000 }
  )
  return response.data
}

/** Process a stopped or failed file again from the start. */
export async function reprocessFile(fileId: string, outputLanguage?: string): Promise<FileInfo> {
  const response = await api.post(`/api/files/${fileId}/reprocess`, { output_language: outputLanguage })
  return response.data
}

export async function updateFile(fileId: string, data: { file_name: string }): Promise<FileInfo> {
  const response = await api.put(`/api/files/${fileId}`, data)
  return response.data
}

export async function getFilesStatusBatch(fileIds: string[]): Promise<{
  files: {
    id: string
    status: string
    error_message?: string
    processing_current?: number | null
    processing_total?: number | null
    processing_message?: string | null
  }[]
}> {
  const response = await api.post('/api/files/status/batch', { file_ids: fileIds })
  return response.data
}


export async function getImageInfo(fileId: string): Promise<ImageFileInfo> {
  const response = await api.get(`/api/files/${fileId}/image-info`)
  return response.data
}


export interface SessionsResponse {
  sessions: Session[]
  total: number
  limit: number
  offset: number
}


export interface SessionDetailResponse extends Session {
  total_messages: number
  raw_fetched?: number
  messages_limit: number
  messages_offset: number
}

export async function getSessions(
  projectId: string,
  limit: number = 50,
  offset: number = 0
): Promise<SessionsResponse> {
  const response = await api.get(`/api/projects/${projectId}/sessions`, {
    params: { limit, offset }
  })
  return response.data
}

export async function getSession(
  sessionId: string,
  limit: number = 50,
  offset: number = 0,
  brief: boolean = false
): Promise<SessionDetailResponse> {
  const params: any = { limit, offset }
  if (brief) {
    params.brief = 1
  }
  const response = await api.get(`/api/sessions/${sessionId}`, {
    params
  })
  return response.data
}

export interface CreateSessionResponse extends Session {
  reused: boolean
}

// New chats are stored with the language-neutral placeholder; the UI shows it translated and
// replaces it with a generated title after the first question.
export async function createSession(projectId: string, title: string = 'New chat'): Promise<CreateSessionResponse> {
  const response = await api.post(`/api/projects/${projectId}/sessions`, { title })
  return response.data
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<Session> {
  const response = await api.put(`/api/sessions/${sessionId}`, { title })
  return response.data
}

export interface GenerateSessionTitleResponse {
  id: string
  title: string | null
  title_generation_status: Session['title_generation_status']
  generated: boolean
}

export interface GenerateSessionTitleRequest {
  question: string
  file_names: string[]
}

export async function generateSessionTitle(
  sessionId: string,
  data: GenerateSessionTitleRequest
): Promise<GenerateSessionTitleResponse> {
  const response = await api.post(`/api/sessions/${sessionId}/title/generate`, data)
  return response.data
}

export async function deleteSession(sessionId: string): Promise<void> {
  await api.delete(`/api/sessions/${sessionId}`)
}


export interface SegmentCitationRef {
  type: 'segment'
  display_num: number
  file_name: string
  segment_id: string
  summary: string
}


export interface AudioCitationRef {
  type: 'audio'
  display_num: number
  file_name: string
  segment_id: string
  summary: string
  time_start?: number
  time_end?: number
  time_range?: string
}


export interface ImageCitationRef {
  type: 'image'
  display_num: number
  file_id: string
  file_name: string

  image_name?: string
  image_index?: number
  page?: number
}


export interface WebCitationRef {
  type: 'web'
  display_num: number
  title: string
  url: string
  snippet: string
  source: string
  published_date: string
  favicon?: string
}

export type CitationRef = SegmentCitationRef | AudioCitationRef | ImageCitationRef | WebCitationRef


export type AgentRole = 'default' | 'analysis'


export interface ChatStreamDoneData {
  agentRole?: AgentRole
  sessionUpdated?: {
    title: string
  }
}

export interface WorkflowStartedData {
  workflow_id: string
  status: string
  display_name?: string
}

export interface FeatureStartedData {
  feature_id: string
  status: string
  display_name?: string
}

export interface ChatStreamCallbacks {
  onContent: (content: string) => void
  onCitationRef?: (citation: CitationRef) => void
  onToolExecuting?: (tools: ToolExecuting[]) => void
  onWorkflowStarted?: (data: WorkflowStartedData) => void
  onFeatureStarted?: (data: FeatureStartedData) => void
  onReasoning?: (content: string) => void
  onReasoningCitationRef?: (citation: CitationRef) => void
  onCompacting?: () => void
  onCompactDone?: () => void
  onCompactFailed?: (message: string) => void
  onDone: (data: ChatStreamDoneData) => void
  onError: (error: string, hasPartial?: boolean) => void
  onMessageIds?: (userMessageId: string, assistantMessageId: string) => void
}

export function chatStream(
  sessionId: string,
  message: string,
  fileIds: string[] | undefined,
  callbacks: ChatStreamCallbacks,
  enableWebSearch: boolean = false,
  agentRole: AgentRole = 'default',
  /** No sources selected: answer from general knowledge, without citations. */
  generalChat: boolean = false
): () => void {
  const controller = new AbortController()
  const token = getToken()

  fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({
      session_id: sessionId,
      message,
      file_ids: fileIds,
      enable_web_search: enableWebSearch,
      agent_role: agentRole,
      output_language: getModelOutputLanguage(),
      general_chat: generalChat
    }),
    signal: controller.signal
  })
    .then(async (response) => {
      if (response.status === 401) {
        clearTokens()
        window.location.href = '/login'
        return
      }
      if (response.status === 429) {
        showGlobalToast(t('ui.tooManyRequestsTryAgainLater'))
        callbacks.onError(t('ui.tooManyRequestsTryAgainLater'))
        return
      }
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No reader available')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              switch (data.type) {
                case 'text':
                  callbacks.onContent(data.content)
                  break
                case 'citation_ref':
                  if (data.citation_type === 'web') {

                    callbacks.onCitationRef?.({
                      type: 'web',
                      display_num: data.display_num,
                      title: data.title,
                      url: data.url,
                      snippet: data.snippet,
                      source: data.source || '',
                      published_date: data.published_date || '',
                      favicon: data.favicon || ''
                    })
                  } else if (data.citation_type === 'image') {

                    callbacks.onCitationRef?.({
                      type: 'image',
                      display_num: data.display_num,
                      file_id: data.file_id,
                      file_name: data.file_name,

                      image_name: data.image_name,
                      image_index: data.image_index,
                      page: data.page
                    })
                  } else if (data.citation_type === 'audio') {

                    callbacks.onCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  } else {

                    callbacks.onCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  }
                  break
                case 'tool_executing':
                  callbacks.onToolExecuting?.(data.tools || [])
                  break
                case 'workflow_started':
                  callbacks.onWorkflowStarted?.(data)
                  break
                case 'feature_started':
                  callbacks.onFeatureStarted?.(data)
                  break
                case 'reasoning':
                  callbacks.onReasoning?.(data.content)
                  break
                case 'reasoning_citation_ref':
                  if (data.citation_type === 'web') {
                    callbacks.onReasoningCitationRef?.({
                      type: 'web',
                      display_num: data.display_num,
                      title: data.title,
                      url: data.url,
                      snippet: data.snippet,
                      source: data.source || '',
                      published_date: data.published_date || '',
                      favicon: data.favicon || ''
                    })
                  } else if (data.citation_type === 'image') {
                    callbacks.onReasoningCitationRef?.({
                      type: 'image',
                      display_num: data.display_num,
                      file_id: data.file_id,
                      file_name: data.file_name,
                      image_name: data.image_name,
                      image_index: data.image_index,
                      page: data.page
                    })
                  } else if (data.citation_type === 'audio') {
                    callbacks.onReasoningCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  } else {
                    callbacks.onReasoningCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  }
                  break
                case 'compacting':
                  callbacks.onCompacting?.()
                  break
                case 'compact_done':
                  callbacks.onCompactDone?.()
                  break
                case 'compact_failed':
                  callbacks.onCompactFailed?.(data.message || '')
                  break
                case 'done':
                  callbacks.onDone({
                    agentRole: data.agent_role,
                    sessionUpdated: data.session_updated
                  })
                  break
                case 'message_ids':
                  callbacks.onMessageIds?.(data.user_message_id, data.assistant_message_id)
                  break
                case 'error':
                  callbacks.onError(data.data || data.message, data.has_partial)
                  break
              }
            } catch {

            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        callbacks.onError(error.message)
      }
    })

  return () => controller.abort()
}


export function editMessageAndRegenerate(
  sessionId: string,
  messageId: string,
  content: string,
  fileIds: string[] | undefined,
  callbacks: ChatStreamCallbacks,
  enableWebSearch: boolean = false,
  agentRole: AgentRole = 'default',
  /** No sources selected: answer from general knowledge, without citations. */
  generalChat: boolean = false
): () => void {
  const controller = new AbortController()
  const token = getToken()

  fetch(`${API_BASE}/api/chat/${sessionId}/messages/${messageId}/edit`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({
      content,
      file_ids: fileIds,
      enable_web_search: enableWebSearch,
      agent_role: agentRole,
      output_language: getModelOutputLanguage(),
      general_chat: generalChat
    }),
    signal: controller.signal
  })
    .then(async (response) => {
      if (response.status === 401) {
        clearTokens()
        window.location.href = '/login'
        return
      }
      if (response.status === 402) {

        const data = await response.json()
        callbacks.onError(data.error || t('ui.pointsInsufficientRecharge'))
        return
      }
      if (response.status === 429) {
        showGlobalToast(t('ui.tooManyRequestsTryAgainLater'))
        callbacks.onError(t('ui.tooManyRequestsTryAgainLater'))
        return
      }
      if (!response.ok) {

        try {
          const data = await response.json()
          callbacks.onError(data.error || `HTTP error! status: ${response.status}`)
        } catch {
          callbacks.onError(`HTTP error! status: ${response.status}`)
        }
        return
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No reader available')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              switch (data.type) {
                case 'text':
                  callbacks.onContent(data.content)
                  break
                case 'citation_ref':
                  if (data.citation_type === 'web') {
                    callbacks.onCitationRef?.({
                      type: 'web',
                      display_num: data.display_num,
                      title: data.title,
                      url: data.url,
                      snippet: data.snippet,
                      source: data.source || '',
                      published_date: data.published_date || '',
                      favicon: data.favicon || ''
                    })
                  } else if (data.citation_type === 'image') {
                    callbacks.onCitationRef?.({
                      type: 'image',
                      display_num: data.display_num,
                      file_id: data.file_id,
                      file_name: data.file_name,

                      image_name: data.image_name,
                      image_index: data.image_index,
                      page: data.page
                    })
                  } else if (data.citation_type === 'audio') {
                    callbacks.onCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  } else {
                    callbacks.onCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  }
                  break
                case 'tool_executing':
                  callbacks.onToolExecuting?.(data.tools || [])
                  break
                case 'workflow_started':
                  callbacks.onWorkflowStarted?.(data)
                  break
                case 'feature_started':
                  callbacks.onFeatureStarted?.(data)
                  break
                case 'reasoning':
                  callbacks.onReasoning?.(data.content)
                  break
                case 'reasoning_citation_ref':
                  if (data.citation_type === 'web') {
                    callbacks.onReasoningCitationRef?.({
                      type: 'web',
                      display_num: data.display_num,
                      title: data.title,
                      url: data.url,
                      snippet: data.snippet,
                      source: data.source || '',
                      published_date: data.published_date || '',
                      favicon: data.favicon || ''
                    })
                  } else if (data.citation_type === 'image') {
                    callbacks.onReasoningCitationRef?.({
                      type: 'image',
                      display_num: data.display_num,
                      file_id: data.file_id,
                      file_name: data.file_name,
                      image_name: data.image_name,
                      image_index: data.image_index,
                      page: data.page
                    })
                  } else if (data.citation_type === 'audio') {
                    callbacks.onReasoningCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  } else {
                    callbacks.onReasoningCitationRef?.({
                      type: 'segment',
                      display_num: data.display_num,
                      file_name: data.file_name,
                      segment_id: data.segment_id,
                      summary: data.summary
                    })
                  }
                  break
                case 'done':
                  callbacks.onDone({
                    agentRole: data.agent_role,
                    sessionUpdated: data.session_updated
                  })
                  break
                case 'message_ids':
                  callbacks.onMessageIds?.(data.user_message_id, data.assistant_message_id)
                  break
                case 'error':
                  callbacks.onError(data.data || data.message, data.has_partial)
                  break
              }
            } catch {

            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        callbacks.onError(error.message)
      }
    })

  return () => controller.abort()
}


export interface FeatureListItem {
  id: string
  feature_type: string
  display_name?: string
  title: string | null
  prompt?: string | null
  note_source?: 'chat' | 'manual' | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message: string | null
  /** What a running job is doing now (deep research) */
  progress?: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}


export async function getProjectFeatures(projectId: string): Promise<{ features: FeatureListItem[] }> {
  const response = await api.get(`/api/features/project/${projectId}`)
  return response.data
}


export async function getFeaturesStatusBatch(featureIds: string[]): Promise<{
  features: Record<string, {
    id: string
    status: string
    error_message: string | null
    display_name?: string
    prompt?: string | null
    title?: string | null
    progress?: string | null
  }>
}> {
  const response = await api.post('/api/features/status/batch', { feature_ids: featureIds })
  return response.data
}


export async function getFeatureContentBatch(featureIds: string[]): Promise<{
  features: Record<string, Feature>
}> {
  const response = await api.post('/api/features/content/batch', { feature_ids: featureIds })
  return response.data
}

export interface FeatureCustomConfig {
  prompt?: string
  title?: string
  file_ids: string[]
  output_language?: string
  aspect_ratio?: string

  duration?: number
  resolution?: string
  bgm?: boolean
}

export async function generateFeature(
  projectId: string,
  featureType: string,
  customConfig: FeatureCustomConfig
): Promise<{ feature_id: string; status: string; display_name?: string }> {
  const response = await api.post('/api/features/generate', {
    project_id: projectId,
    feature_type: featureType,
    custom_config: customConfig
      ? { ...customConfig, output_language: customConfig.output_language || getModelOutputLanguage() }
      : customConfig
  }, { timeout: 60000 })
  return response.data
}

export async function getFeature(featureId: string): Promise<Feature> {
  const response = await api.get(`/api/features/${featureId}`)
  return response.data
}

export async function getFeatureByType(projectId: string, featureType: string): Promise<{ feature: Feature | null }> {
  const response = await api.get(`/api/features/project/${projectId}/type/${featureType}`)
  return response.data
}


export async function getFeatureListByType(projectId: string, featureType: string): Promise<{
  features: Array<{ id: string; title: string; status: string; created_at: string }>
}> {
  const response = await api.get(`/api/features/project/${projectId}/type/${featureType}/list`)
  return response.data
}

export async function deleteFeature(featureId: string): Promise<void> {
  await api.delete(`/api/features/${featureId}`)
}

/** Save a chat answer (by message id) or free-form markdown as a note in the project. */
export async function createNote(
  projectId: string,
  data: { messageId?: string; content?: string; title?: string }
): Promise<FeatureListItem> {
  const response = await api.post('/api/features/notes', {
    project_id: projectId,
    message_id: data.messageId,
    content: data.content,
    title: data.title,
  })
  return response.data
}

/** Re-run a quick tool in place with the sources and prompt it was created with. */
export async function regenerateFeature(featureId: string): Promise<FeatureListItem> {
  const response = await api.post(`/api/features/${featureId}/regenerate`)
  return response.data
}

export interface SourceReference {
  name: string
  file_type: string
  page: number | null
  volume: number | null
  page_kind: 'pdf' | 'printed' | null
  sentence: string
}

/** Work name, page and a verbatim sentence for each citation of a result or note (for downloads). */
export async function getFeatureReferences(featureId: string): Promise<Record<string, SourceReference>> {
  const response = await api.get(`/api/features/${featureId}/references`)
  return response.data?.references || {}
}

export async function updateFeature(featureId: string, data: { title?: string; content?: string }): Promise<{ id: string; title: string; updated_at: string }> {
  const response = await api.put(`/api/features/${featureId}`, data)
  return response.data
}

export interface ImageInfo {
  file_id: string
  file_name: string
  file_type: string
  width: number
  height: number
  format: string
  file_size: number
  description: string
  tags: string[]
  scene_type: string
  style: string
  ocr_text: string
  analysis_status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message: string | null
  preview_url: string
}


export function getImagePreviewUrl(fileId: string): string {
  const token = getMediaToken()
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${API_BASE}/api/files/${fileId}/preview${query}`
}

export function getAudioPreviewUrl(fileId: string): string {
  const token = getMediaToken()
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${API_BASE}/api/files/${fileId}/preview${query}`
}

export function getEmbeddedImagePreviewUrl(fileId: string, imageIndex: number): string {
  const token = getMediaToken()
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${API_BASE}/api/files/${fileId}/images/${imageIndex}/preview${query}`
}


export function getAssetUrl(path: string): string {
  if (!path) return ''

  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }

  const base = `${API_BASE}${path.startsWith('/') ? '' : '/'}${path}`
  if (path.startsWith('/api/')) {
    const token = getMediaToken()
    if (token && !base.includes('token=')) {
      const sep = base.includes('?') ? '&' : '?'
      return `${base}${sep}token=${encodeURIComponent(token)}`
    }
  }
  return base
}


const PDF_CACHE_MAX_SIZE = 5
const PDF_CACHE_TTL = 30 * 60 * 1000


interface PdfCacheItem {
  data: ArrayBuffer
  timestamp: number
  accessTime: number
}


const pdfCache = new Map<string, PdfCacheItem>()


function cleanExpiredPdfCache() {
  const now = Date.now()
  for (const [key, item] of pdfCache.entries()) {
    if (now - item.timestamp > PDF_CACHE_TTL) {
      pdfCache.delete(key)
    }
  }
}


function evictLruPdfCache() {
  if (pdfCache.size < PDF_CACHE_MAX_SIZE) return

  let oldestKey: string | null = null
  let oldestTime = Infinity

  for (const [key, item] of pdfCache.entries()) {
    if (item.accessTime < oldestTime) {
      oldestTime = item.accessTime
      oldestKey = key
    }
  }

  if (oldestKey) {
    pdfCache.delete(oldestKey)
  }
}


export async function getPdfRawData(fileId: string): Promise<ArrayBuffer> {

  cleanExpiredPdfCache()


  const cached = pdfCache.get(fileId)
  if (cached) {

    cached.accessTime = Date.now()

    return cached.data.slice(0)
  }


  const response = await api.get(`/api/files/${fileId}/raw`, {
    responseType: 'arraybuffer'
  })


  evictLruPdfCache()


  const now = Date.now()
  pdfCache.set(fileId, {
    data: (response.data as ArrayBuffer).slice(0),
    timestamp: now,
    accessTime: now
  })

  return response.data
}


export function clearPdfCache(fileId?: string) {
  if (fileId) {
    pdfCache.delete(fileId)
  } else {
    pdfCache.clear()
  }
}


export interface BlockBboxInfo {
  page: number
  bbox: [number, number, number, number] | null
}


export async function getBlocksBbox(
  fileId: string,
  blockIds?: string[]
): Promise<{ file_id: string; file_type: string; blocks: Record<string, BlockBboxInfo> }> {
  const response = await api.post(`/api/files/${fileId}/blocks/bbox`, {
    block_ids: blockIds
  })
  return response.data
}


export interface FoundBlock {
  block_id: string
  content: string
  page: number
  bbox: [number, number, number, number]
}

export interface FindBlockByPositionResponse {
  found: boolean
  block: FoundBlock | null
}

export async function findBlockByPosition(
  fileId: string,
  page: number,
  x: number,
  y: number
): Promise<FindBlockByPositionResponse> {
  const response = await api.post(`/api/files/${fileId}/blocks/find-by-position`, {
    page,
    x,
    y
  })
  return response.data
}


export interface WorkflowProgress {
  total: number
  completed: number
  failed: number
  cancelled?: number
  current_step: string | null
}


export interface WorkflowStep {
  step_index: number
  step_id?: string | null
  depends_on?: string[]
  step_name: string
  feature_id: string | null
  feature_type: string
  display_name: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  title: string | null
  error_message: string | null
}


export type WorkflowStatus = 'pending' | 'processing' | 'cancelling' | 'completed' | 'failed' | 'partial' | 'cancelled'


export interface CreateWorkflowResponse {
  workflow_id: string
  workflow_type: string
  display_name: string
  status: WorkflowStatus
  steps_count: number
  is_finalized?: boolean
}


export interface WorkflowStatusResponse {
  id: string
  status: WorkflowStatus
  progress: WorkflowProgress
}


export interface WorkflowDetail {
  id: string
  workflow_type: string
  display_name: string
  title?: string | null
  status: WorkflowStatus
  progress: WorkflowProgress
  steps: WorkflowStep[]
  created_at: string
  finished_at: string | null
  is_finalized?: boolean
}


export interface WorkflowListItem {
  id: string
  workflow_type: string
  display_name: string
  status: WorkflowStatus
  progress: WorkflowProgress
  created_at: string
  finished_at: string | null
  title?: string | null
  is_finalized?: boolean
}


export async function renameWorkflow(workflowId: string, title: string): Promise<WorkflowListItem> {
  const response = await api.put(`/api/workflows/${workflowId}/title`, { title })
  return response.data
}


export async function finalizeWorkflow(workflowId: string): Promise<{ success: boolean, is_finalized: boolean }> {
  const response = await api.put(`/api/workflows/${workflowId}/finalized`, { is_finalized: true })
  return response.data
}


export async function createWorkflow(
  projectId: string,
  title: string,
  customConfig?: {
    prompt?: string
    file_ids?: string[]
    preset_key?: string
    output_language?: string
  }
): Promise<CreateWorkflowResponse> {
  const response = await api.post('/api/workflows/generate', {
    project_id: projectId,
    title,
    custom_config: customConfig
  }, { timeout: 60000 })
  return response.data
}


export async function getWorkflowStatus(workflowId: string): Promise<WorkflowStatusResponse> {
  const response = await api.get(`/api/workflows/${workflowId}/status`)
  return response.data
}


export async function getWorkflowsStatusBatch(workflowIds: string[]): Promise<{
  workflows: Record<string, WorkflowStatusResponse>
}> {
  const response = await api.post('/api/workflows/status/batch', {
    workflow_ids: workflowIds
  })
  return response.data
}


export async function getWorkflowDetail(workflowId: string): Promise<WorkflowDetail> {
  const response = await api.get(`/api/workflows/${workflowId}`)
  return response.data
}


export async function getProjectWorkflows(projectId: string): Promise<{ workflows: WorkflowListItem[] }> {
  const response = await api.get(`/api/workflows/project/${projectId}`)
  return response.data
}


export async function cancelWorkflow(workflowId: string): Promise<WorkflowStatusResponse> {
  const response = await api.post(`/api/workflows/${workflowId}/cancel`)
  return response.data
}


export async function retryWorkflowStep(
  workflowId: string,
  stepIndex: number
): Promise<{ success: boolean; message: string }> {
  const response = await api.post(`/api/workflows/${workflowId}/steps/${stepIndex}/retry`)
  return response.data
}


export async function regenerateWorkflowStep(
  workflowId: string,
  stepIndex: number,
  customConfig?: Record<string, any>
): Promise<{ success: boolean; feature_id: string; step_name: string; previous_status: string }> {
  const body = customConfig ? { custom_config: customConfig } : {}
  const response = await api.post(`/api/workflows/${workflowId}/steps/${stepIndex}/regenerate`, body)
  return response.data
}


export async function getWorkflowStepConfig(
  workflowId: string,
  stepIndex: number
): Promise<{
  workflow_id: string
  step_index: number
  step_name: string
  feature_id: string | null
  feature_type: string
  custom_config?: Record<string, any>
}> {
  const response = await api.get(`/api/workflows/${workflowId}/steps/${stepIndex}/config`)
  return response.data
}


export async function deleteWorkflow(workflowId: string): Promise<void> {
  await api.delete(`/api/workflows/${workflowId}`)
}


export interface FeatureEditCitationRef {
  type: 'citation_ref'
  display_num: number
  citation_id: string
  file_name?: string
  segment_id?: string
  summary?: string
  citation_type?: 'audio' | 'image' | 'web'
  time_start?: number
  time_end?: number
  time_range?: string

  file_id?: string

  title?: string
  url?: string
  snippet?: string
  source?: string
  published_date?: string
}


export interface FeatureEditHistoryMessage {
  role: 'user' | 'assistant'
  content: string
  content_parts?: Array<{ type: 'text'; content: string } | FeatureEditCitationRef>
  tool_executing?: Array<{
    name: string
    display: string
    display_key?: string
    display_params?: Record<string, unknown>
    displayKey?: string
    displayParams?: Record<string, unknown>
  }>
}


export interface EditPreviewContentPart {
  type: 'text' | 'citation_ref'
  content?: string
  display_num?: number
  citation_id?: string
  file_name?: string
  segment_id?: string
  summary?: string
}


export interface FeatureEditCallbacks {
  onStart?: () => void
  onText?: (text: string) => void
  onCitationRef?: (citation: FeatureEditCitationRef) => void
  onToolExecuting?: (tools: ToolExecuting[]) => void
  onEditPreview?: (data: {
    block_index: number
    old_content: string
    new_content: string
    old_content_parts: EditPreviewContentPart[]
    new_content_parts: EditPreviewContentPart[]
  }) => void
  onEditApplied?: (data: { block_index: number; new_content: string; block: FeatureBlock; success: boolean; error?: string }) => void
  onDone?: (data: {
    session_id: string
    history: FeatureEditHistoryMessage[]
    citations?: Record<string, any>
    next_citation_display_num?: number
  }) => void
  onError?: (error: string) => void
}


export async function featureEditChat(
  featureId: string,
  message: string,
  callbacks: FeatureEditCallbacks,
  sessionId?: string | null
): Promise<void> {
  const token = getToken()


  const requestBody: { message: string; session_id?: string } = { message }
  if (sessionId) {
    requestBody.session_id = sessionId
  }

  const response = await fetch(`${API_BASE}/api/features/${featureId}/edit/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(requestBody)
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') {
          return
        }

        try {
          const event = JSON.parse(data)
          switch (event.type) {
            case 'start':
              callbacks.onStart?.()
              break
            case 'text':
              callbacks.onText?.(event.content)
              break
            case 'citation_ref':

              callbacks.onCitationRef?.(event as FeatureEditCitationRef)
              break
            case 'tool_executing':
              callbacks.onToolExecuting?.(event.tools || [])
              break
            case 'edit_preview':
              callbacks.onEditPreview?.(event)
              break
            case 'edit_applied':
              callbacks.onEditApplied?.(event)
              break
            case 'done':
              callbacks.onDone?.(event)
              break
            case 'error':
              callbacks.onError?.(event.message)
              break
          }
        } catch (e) {
          console.error('Parse SSE error:', e)
        }
      }
    }
  }
}


export interface WorkflowCitation {
  display_num: number
  file_name: string
  file_id?: string
  segment_id: string
  summary?: string
  start_page?: number
  content?: string
  type?: 'image' | 'pdf_image' | 'web' | 'segment'
  media_type?: 'audio'
  citation_type?: 'audio'
  time_start?: number
  time_end?: number
  time_range?: string
  image_name?: string
  image_index?: number
  page?: number
}


export interface WorkflowContentFeature {
  id: string
  project_id: string
  feature_type: string
  step_index: number
  step_id?: string | null
  depends_on?: string[]
  step_name: string
  title: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'
  error_message?: string
  blocks: FeatureBlock[]
  citations: Record<string, WorkflowCitation>
}


export interface WorkflowContentResponse {
  workflow_id: string
  citations: Record<string, WorkflowCitation>
  features: WorkflowContentFeature[]
}


export interface WorkflowContentStep {
  step_index: number
  step_name: string
  feature: {
    id: string
    feature_type: string
    title: string
    generation_report: string
  }
  blocks: FeatureBlock[]
}

export interface WorkflowContent {
  workflow: {
    id: string
    workflow_type: string
    title: string
    project_id: string
    status: string
    citations: Record<string, WorkflowCitation>
    next_citation_display_num: number
  }
  steps: WorkflowContentStep[]
}


export async function getWorkflowContent(workflowId: string): Promise<WorkflowContentResponse> {
  const response = await api.get(`/api/workflows/${workflowId}/content`)
  return response.data
}


export async function getWorkflowEditContext(workflowId: string): Promise<WorkflowContent> {
  const response = await api.get(`/api/workflows/${workflowId}/edit/context`)
  return response.data
}


export interface WorkflowEditCallbacks {
  onStart?: () => void
  onText?: (text: string) => void
  onCitationRef?: (citation: FeatureEditCitationRef) => void
  onToolExecuting?: (tools: ToolExecuting[]) => void
  onEditPreview?: (data: {
    step_index: number
    step_name: string
    block_index: number
    old_content: string
    new_content: string
    old_content_parts: EditPreviewContentPart[]
    new_content_parts: EditPreviewContentPart[]
  }) => void
  onEditApplied?: (data: {
    step_index: number
    step_name: string
    block_index: number
    success: boolean
    new_content: string
    block: FeatureBlock
    error?: string
  }) => void
  onDone?: (data: {
    session_id: string
    history: FeatureEditHistoryMessage[]
    citations: Record<string, WorkflowCitation>
    next_citation_display_num: number
  }) => void
  onError?: (error: string) => void
}


export async function workflowEditChat(
  workflowId: string,
  message: string,
  callbacks: WorkflowEditCallbacks,
  sessionId?: string | null
): Promise<void> {
  const token = getToken()


  const requestBody: { message: string; session_id?: string } = { message }
  if (sessionId) {
    requestBody.session_id = sessionId
  }

  const response = await fetch(`${API_BASE}/api/workflows/${workflowId}/edit/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify(requestBody)
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') {
          return
        }

        try {
          const event = JSON.parse(data)
          switch (event.type) {
            case 'start':
              callbacks.onStart?.()
              break
            case 'text':
              callbacks.onText?.(event.content)
              break
            case 'citation_ref':
              callbacks.onCitationRef?.(event as FeatureEditCitationRef)
              break
            case 'tool_executing':
              callbacks.onToolExecuting?.(event.tools || [])
              break
            case 'edit_preview':

              callbacks.onEditPreview?.(event)
              break
            case 'edit_applied':

              callbacks.onEditApplied?.(event)
              break
            case 'done':

              callbacks.onDone?.(event)
              break
            case 'error':
              callbacks.onError?.(event.message)
              break
          }
        } catch (e) {
          console.error('Parse SSE error:', e)
        }
      }
    }
  }
}


export interface EditSession {
  id: string
  title: string
  message_count: number
  created_at: string
  updated_at: string
}


export interface EditSessionsResponse {
  sessions: EditSession[]
  total: number
}


export interface FeatureEditChange {
  block_index: number
  old_content: string
  new_content: string
  reason?: string
  success: boolean
  error_message?: string | null
  is_outdated?: boolean
}


export interface WorkflowEditChange extends FeatureEditChange {
  step_index: number
  step_name: string
}


export interface EditSessionMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  content_parts?: Array<{
    type: 'text' | 'citation_ref'
    content?: string
    display_num?: number
    citation_id?: string
    file_name?: string
    segment_id?: string
    summary?: string
  }>
  tool_calls?: Array<{
    id: string
    name: string
    arguments: Record<string, any>
  }>
  tool_executing?: Array<{
    name: string
    display: string
    display_key?: string
    display_params?: Record<string, unknown>
    displayKey?: string
    displayParams?: Record<string, unknown>
  }>
  tool_call_id?: string
  name?: string
  citations?: Record<string, any>
  changes?: FeatureEditChange[] | WorkflowEditChange[]
  created_at: string
}


export interface EditSessionDetailResponse {
  session: EditSession
  messages: EditSessionMessage[]
}


export async function getFeatureEditSessions(
  featureId: string,
  limit: number = 20,
  offset: number = 0
): Promise<EditSessionsResponse> {
  const response = await api.get(`/api/features/${featureId}/edit/sessions`, {
    params: { limit, offset }
  })
  return response.data
}


export async function getFeatureEditSessionDetail(
  featureId: string,
  sessionId: string
): Promise<EditSessionDetailResponse> {
  const response = await api.get(`/api/features/${featureId}/edit/sessions/${sessionId}`)
  return response.data
}


export async function getWorkflowEditSessions(
  workflowId: string,
  limit: number = 20,
  offset: number = 0
): Promise<EditSessionsResponse> {
  const response = await api.get(`/api/workflows/${workflowId}/edit/sessions`, {
    params: { limit, offset }
  })
  return response.data
}


export async function getWorkflowEditSessionDetail(
  workflowId: string,
  sessionId: string
): Promise<EditSessionDetailResponse> {
  const response = await api.get(`/api/workflows/${workflowId}/edit/sessions/${sessionId}`)
  return response.data
}


export type CitationStyle = 'inline' | 'endnote'


export async function exportWorkflowToWord(
  workflowId: string,
  options: {
    include_citations?: boolean
    citation_style?: CitationStyle
    output_language?: string
  } = {}
): Promise<{ blob: Blob; filename: string }> {
  const response = await api.post(
    `/api/workflows/${workflowId}/export`,
    {
      include_citations: options.include_citations ?? true,
      citation_style: options.citation_style ?? 'inline',
      output_language: options.output_language ?? getModelOutputLanguage()
    },
    {
      responseType: 'blob',
      timeout: 120000
    }
  )


  const contentDisposition = response.headers['content-disposition']
  let filename = 'workflow.docx'
  if (contentDisposition) {

    const utf8Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
    if (utf8Match && utf8Match[1]) {
      filename = decodeURIComponent(utf8Match[1])
    } else {

      const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '')
        try {
          filename = decodeURIComponent(filename)
        } catch {
        }
      }
    }
  }

  return {
    blob: response.data,
    filename
  }
}

/** Speech to text for the chat box (uses the speech recognition service from Settings). */
export async function transcribeDictation(audio: Blob): Promise<string> {
  const form = new FormData()
  const extension = audio.type.includes('wav') ? 'wav' : audio.type.includes('mp4') ? 'm4a' : 'webm'
  form.append('file', audio, `dictation.${extension}`)
  const response = await api.post('/api/chat/transcribe', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  })
  return response.data?.text || ''
}

export async function exportChatMessagesToWord(
  sessionId: string,
  userMessageIds: string[] | null = null,
  includeCitations: boolean = true,
  outputLanguage: string = getModelOutputLanguage()
): Promise<{ blob: Blob; filename: string }> {
  const response = await api.post(
    `/api/sessions/${sessionId}/export`,
    {
      user_message_ids: userMessageIds,
      include_citations: includeCitations,
      output_language: outputLanguage
    },
    {
      responseType: 'blob',
      timeout: 120000
    }
  )

  const contentDisposition = response.headers['content-disposition']
  let filename = 'chat_export.docx'
  if (contentDisposition) {
    const utf8Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
    if (utf8Match && utf8Match[1]) {
      filename = decodeURIComponent(utf8Match[1])
    } else {
      const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '')
        try {
          filename = decodeURIComponent(filename)
        } catch {
        }
      }
    }
  }

  return {
    blob: response.data,
    filename
  }
}


export interface SettingsMap {
  llm_api_key?: string
  llm_base_url?: string
  llm_model?: string
  llm_api_format?: string
  easy_task_llm?: string
  easy_task_llm_verified?: string
  vlm_api_key?: string
  vlm_base_url?: string
  vlm_model?: string
  embedding_source?: string
  embedding_model?: string
  embedding_api_key?: string
  embedding_base_url?: string
  embedding_local_url?: string
  ocr_base_url?: string
  ocr_api_key?: string
  ocr_model?: string
  funasr_base_url?: string
  funasr_api_key?: string
  funasr_model?: string
  funasr_verified?: string
  tts_base_url?: string
  tts_api_key?: string
  tts_model?: string
  tts_voice?: string
  tts_verified?: string
  searxng_base_url?: string
  [key: string]: string | undefined
}

export interface PreflightResult {
  ready: boolean
  llm_ready: boolean
  embedding_ready: boolean
  web_search_ready?: boolean
  missing: string[]
}

export async function checkPreflight(): Promise<PreflightResult> {
  const response = await api.get('/api/settings/preflight')
  return response.data
}

export async function getSettings(): Promise<SettingsMap> {
  const response = await api.get('/api/settings')
  return response.data.settings
}

export async function updateSettings(settings: Partial<SettingsMap>, force = false): Promise<SettingsMap> {
  const response = await api.patch('/api/settings', { settings, force })
  return response.data.settings
}

export async function getSettingRaw(key: string): Promise<string | null> {
  const response = await api.get(`/api/settings/${key}`)
  return response.data.value
}
