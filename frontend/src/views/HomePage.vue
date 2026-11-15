<template>
  <div class="home-page">
    <header class="home-header">
      <AppLogo />
      <AppHeaderActions current="home" />
    </header>

    <main class="home-main">
      <section class="hero">
        <div class="hero-copy">
          <h1 class="hero-title">{{ $t('ui.homeHeroTitle') }}</h1>
          <p class="hero-subtitle">{{ $t('ui.homeHeroSubtitle') }}</p>
        </div>
        <div class="hero-actions">
          <label v-if="projects.length > 0" class="search-field">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z" />
            </svg>
            <input
              v-model="searchQuery"
              type="search"
              :placeholder="$t('ui.searchProjects')"
              :aria-label="$t('ui.searchProjects')"
            />
          </label>
          <button class="btn btn-filled" type="button" @click="showCreateModal = true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
              <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
            </svg>
            {{ $t('ui.newProject') }}
          </button>
        </div>
      </section>

      <section class="projects-section">
        <div v-if="loading" class="projects-grid" aria-busy="true">
          <div v-for="n in 4" :key="n" class="project-card project-card--skeleton">
            <div class="skeleton" style="width: 44px; height: 44px; border-radius: 12px"></div>
            <div class="skeleton" style="width: 70%; height: 18px; margin-top: 28px"></div>
            <div class="skeleton" style="width: 100%; height: 12px; margin-top: 12px"></div>
            <div class="skeleton" style="width: 45%; height: 12px; margin-top: 8px"></div>
          </div>
        </div>

        <div v-else-if="loadFailed" class="empty-state">
          <div class="empty-icon empty-icon--error">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor" aria-hidden="true">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
          </div>
          <h2>{{ $t('ui.operationFailed') }}</h2>
          <button class="btn btn-outline" type="button" @click="loadProjects()">{{ $t('ui.retry') }}</button>
        </div>

        <div v-else-if="projects.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="currentColor" aria-hidden="true">
              <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
            </svg>
          </div>
          <h2>{{ $t('ui.noProjectsYet') }}</h2>
          <p>{{ $t('ui.emptyProjectsHint') }}</p>
          <button class="btn btn-filled" type="button" @click="showCreateModal = true">
            {{ $t('ui.createYourFirstProject') }}
          </button>
        </div>

        <div v-else-if="groupedProjects.length === 0" class="empty-state empty-state--compact">
          <p>{{ $t('ui.noMatchingProjects', { query: searchQuery.trim() }) }}</p>
          <button class="btn btn-text" type="button" @click="searchQuery = ''">{{ $t('ui.clearSearch') }}</button>
        </div>

        <div v-else class="projects-container">
          <div v-for="(group, index) in groupedProjects" :key="group.label" class="project-group">
            <h2 class="group-title">{{ group.label }}</h2>
            <div class="projects-grid">
              <button
                v-if="index === 0 && !searchQuery.trim()"
                class="project-card new-card"
                type="button"
                @click="showCreateModal = true"
              >
                <span class="new-icon">
                  <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true">
                    <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
                  </svg>
                </span>
                <span>{{ $t('ui.newProject') }}</span>
              </button>

              <article
                v-for="project in group.projects"
                :key="project.id"
                class="project-card"
                :class="[project.color ? `theme-${project.color}` : 'theme-default', { 'menu-open': activeProjectMenu === project.id }]"
                tabindex="0"
                role="link"
                :aria-label="project.name"
                @click="goToProject(project.id)"
                @keydown.enter.self="goToProject(project.id)"
              >
                <div class="card-icon" :style="{ color: getProjectColor(project.color) }">
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
                    <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
                  </svg>
                </div>
                <h3 class="card-title" dir="auto" :title="project.name">{{ project.name }}</h3>
                <p class="card-summary" dir="auto" :title="project.summary || undefined">{{ project.summary }}</p>
                <p class="card-meta">
                  {{ formatDate(project.created_at) }} · {{ formatFileCount(project.file_count) }}
                </p>

                <div class="card-menu-wrapper">
                  <button
                    class="card-menu-btn"
                    type="button"
                    :title="$t('ui.moreActions')"
                    :aria-label="$t('ui.moreActions')"
                    @click.stop="toggleProjectMenu(project.id)"
                  >
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
                      <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z" />
                    </svg>
                  </button>
                  <div v-if="activeProjectMenu === project.id" class="card-dropdown-menu" role="menu">
                    <button class="card-dropdown-item" type="button" role="menuitem" @click.stop="openRenameModal(project)">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
                        <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" />
                      </svg>
                      {{ $t('ui.rename') }}
                    </button>
                    <button class="card-dropdown-item danger" type="button" role="menuitem" @click.stop="requestDeleteProject(project)">
                      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
                        <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z" />
                      </svg>
                      {{ $t('ui.delete') }}
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </div>
      </section>
    </main>

    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal" role="dialog" aria-modal="true">
        <h3 class="modal-title">{{ $t('ui.newProject') }}</h3>
        <input
          ref="inputRef"
          v-model="newProjectName"
          type="text"
          class="modal-input"
          :placeholder="$t('ui.enterProjectName')"
          @keydown.enter="handleCreateEnter"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
        />
        <div class="modal-actions">
          <button class="btn btn-text" type="button" @click="showCreateModal = false">{{ $t('ui.cancel') }}</button>
          <button
            class="btn btn-filled"
            type="button"
            :disabled="!newProjectName.trim() || creating"
            @click="handleCreateProject"
          >
            {{ creating ? $t('ui.creating') : $t('ui.create') }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showPreflightWarning" class="modal-overlay" @click.self="showPreflightWarning = false">
      <div class="modal" role="dialog" aria-modal="true">
        <h3 class="modal-title">{{ $t('ui.basicConfigurationIsIncomplete') }}</h3>
        <p class="preflight-desc">
          {{ canAdmin ? $t('ui.completeTheFollowingConfigurationBeforeCreatingAProject') : $t('ui.systemConfigurationIncompleteContactAdmin') }}
        </p>
        <ul class="preflight-list">
          <li v-for="item in preflightMissing" :key="item">{{ item }}</li>
        </ul>
        <div class="modal-actions">
          <button class="btn btn-text" type="button" @click="showPreflightWarning = false">{{ $t('ui.later') }}</button>
          <button v-if="canAdmin" class="btn btn-filled" type="button" @click="goToSettings">{{ $t('ui.goToSettings') }}</button>
        </div>
      </div>
    </div>

    <div v-if="showRenameModal" class="modal-overlay" @click.self="closeRenameModal">
      <div class="modal" role="dialog" aria-modal="true">
        <h3 class="modal-title">{{ $t('ui.renameProject') }}</h3>
        <input
          ref="renameInputRef"
          v-model="renameProjectName"
          type="text"
          class="modal-input"
          :placeholder="$t('ui.enterANewProjectName')"
          @keydown.enter="handleRenameEnter"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
        />
        <div class="modal-actions">
          <button class="btn btn-text" type="button" @click="closeRenameModal">{{ $t('ui.cancel') }}</button>
          <button
            class="btn btn-filled"
            type="button"
            :disabled="!renameProjectName.trim() || renaming"
            @click="handleRenameProject"
          >
            {{ renaming ? $t('ui.saving') : $t('ui.save') }}
          </button>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :visible="deleteTarget !== null"
      type="danger"
      :title="$t('ui.confirmDeleteProject')"
      :message="deleteTarget?.name || ''"
      :confirm-text="$t('ui.delete')"
      :cancel-text="$t('ui.cancel')"
      @confirm="confirmDeleteProject"
      @cancel="deleteTarget = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getProjects, createProject, deleteProject, updateProject, checkPreflight } from '../services/api'
import type { Project, ProjectColor } from '../types'
import AppLogo from '../components/common/AppLogo.vue'
import AppHeaderActions from '../components/common/AppHeaderActions.vue'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'
import { formatDate, parseServerDate } from '../utils/format'
import { usePollingTask } from '../composables/usePollingTask'
import { isAdmin } from '../services/auth'
import { useEscapeClose } from '../composables/useEscapeClose'
import { t } from '../i18n'

const router = useRouter()
const canAdmin = computed(() => isAdmin())

const projects = ref<Project[]>([])
const loading = ref(true)
const loadFailed = ref(false)
const searchQuery = ref('')
const deleteTarget = ref<Project | null>(null)

function notify(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'error') {
  window.dispatchEvent(new CustomEvent('global-toast', { detail: { message, type } }))
}
const showCreateModal = ref(false)
const newProjectName = ref('')
const creating = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

const ACTIVE_PROJECT_REFRESH_MS = 10000
const IDLE_PROJECT_REFRESH_MS = 30000


const activeProjectMenu = ref<string | null>(null)


const showRenameModal = ref(false)
const renameProjectId = ref<string | null>(null)
const renameProjectName = ref('')
const renaming = ref(false)
const renameInputRef = ref<HTMLInputElement | null>(null)


const isComposing = ref(false)


interface ProjectGroup {
  label: string
  projects: Project[]
}


const groupedProjects = computed((): ProjectGroup[] => {
  if (projects.value.length === 0) return []

  const query = searchQuery.value.trim().toLocaleLowerCase()
  const visible = query
    ? projects.value.filter((project) =>
        project.name.toLocaleLowerCase().includes(query) ||
        (project.summary || '').toLocaleLowerCase().includes(query)
      )
    : projects.value

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000)
  const dayBeforeYesterday = new Date(today.getTime() - 2 * 24 * 60 * 60 * 1000)
  const threeDaysAgo = new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000)
  const sevenDaysAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)
  const thirtyDaysAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000)

  const todayList: Project[] = []
  const yesterdayList: Project[] = []
  const dayBeforeYesterdayList: Project[] = []
  const threeDaysList: Project[] = []
  const sevenDaysList: Project[] = []
  const thirtyDaysList: Project[] = []
  const olderList: Project[] = []

  
  const sorted = [...visible].sort((a, b) => {
    return parseServerDate(b.updated_at).getTime() - parseServerDate(a.updated_at).getTime()
  })

  for (const project of sorted) {
    const updatedAt = parseServerDate(project.updated_at)

    if (updatedAt >= today) {
      todayList.push(project)
    } else if (updatedAt >= yesterday) {
      yesterdayList.push(project)
    } else if (updatedAt >= dayBeforeYesterday) {
      dayBeforeYesterdayList.push(project)
    } else if (updatedAt >= threeDaysAgo) {
      threeDaysList.push(project)
    } else if (updatedAt >= sevenDaysAgo) {
      sevenDaysList.push(project)
    } else if (updatedAt >= thirtyDaysAgo) {
      thirtyDaysList.push(project)
    } else {
      olderList.push(project)
    }
  }

  
  const result: ProjectGroup[] = []
  if (todayList.length > 0) result.push({ label: t('ui.today'), projects: todayList })
  if (yesterdayList.length > 0) result.push({ label: t('ui.yesterday'), projects: yesterdayList })
  if (dayBeforeYesterdayList.length > 0) result.push({ label: t('ui.twoDaysAgo'), projects: dayBeforeYesterdayList })
  if (threeDaysList.length > 0) result.push({ label: t('ui.last3Days'), projects: threeDaysList })
  if (sevenDaysList.length > 0) result.push({ label: t('ui.last7Days'), projects: sevenDaysList })
  if (thirtyDaysList.length > 0) result.push({ label: t('ui.lastMonth'), projects: thirtyDaysList })
  if (olderList.length > 0) result.push({ label: t('ui.older'), projects: olderList })

  return result
})


function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.card-menu-wrapper')) {
    activeProjectMenu.value = null
  }
}

function needsActiveProjectRefresh(project: Project): boolean {
  return project.file_count > 0 && (!project.summary || !project.color)
}

function getProjectRefreshDelay(): number {
  return projects.value.some(needsActiveProjectRefresh)
    ? ACTIVE_PROJECT_REFRESH_MS
    : IDLE_PROJECT_REFRESH_MS
}

const projectRefresh = usePollingTask({
  run: () => loadProjects({ silent: true }),
  getDelay: getProjectRefreshDelay,
  retryDelay: ACTIVE_PROJECT_REFRESH_MS,
  canRun: () => !loading.value,
  pauseWhenHidden: true,
  refreshOnVisible: true,
  onError: (error) => console.error('Failed to refresh projects:', error),
})

onMounted(() => {
  void loadProjects().finally(() => projectRefresh.start())
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  projectRefresh.stop()
  document.removeEventListener('click', handleClickOutside)
})

watch(showCreateModal, (val) => {
  if (val) {
    nextTick(() => {
      inputRef.value?.focus()
    })
  }
})

watch(showRenameModal, (val) => {
  if (val) {
    nextTick(() => {
      renameInputRef.value?.focus()
      renameInputRef.value?.select()
    })
  }
})

async function loadProjects(options: { silent?: boolean } = {}) {
  try {
    if (!options.silent) loading.value = true
    projects.value = await getProjects()
    loadFailed.value = false
  } catch (error) {
    console.error('Failed to load projects:', error)
    if (!options.silent) loadFailed.value = true
  } finally {
    if (!options.silent) loading.value = false
  }
}


function handleCreateEnter() {
  if (isComposing.value) return
  handleCreateProject()
}


const showPreflightWarning = ref(false)
const preflightMissing = ref<string[]>([])

async function handleCreateProject() {
  if (!newProjectName.value.trim()) return

  try {
    creating.value = true

    
    const preflight = await checkPreflight()
    if (!preflight.ready) {
      preflightMissing.value = preflight.missing
      showPreflightWarning.value = true
      return
    }

    const project = await createProject(newProjectName.value.trim())
    projects.value.unshift(project)
    newProjectName.value = ''
    showCreateModal.value = false
    router.push(`/project/${project.id}`)
  } catch (error) {
    console.error('Failed to create project:', error)
    notify(t('ui.operationFailed'))
  } finally {
    creating.value = false
  }
}

function goToSettings() {
  showPreflightWarning.value = false
  showCreateModal.value = false
  router.push('/settings')
}

function requestDeleteProject(project: Project) {
  activeProjectMenu.value = null
  deleteTarget.value = project
}

async function confirmDeleteProject() {
  const target = deleteTarget.value
  deleteTarget.value = null
  if (!target) return

  try {
    await deleteProject(target.id)
    projects.value = projects.value.filter((p) => p.id !== target.id)
  } catch (error) {
    console.error('Failed to delete project:', error)
    notify(t('ui.deleteFailed'))
  }
}


function toggleProjectMenu(projectId: string) {
  if (activeProjectMenu.value === projectId) {
    activeProjectMenu.value = null
  } else {
    activeProjectMenu.value = projectId
  }
}


function openRenameModal(project: Project) {
  activeProjectMenu.value = null
  renameProjectId.value = project.id
  renameProjectName.value = project.name
  showRenameModal.value = true
}


function closeRenameModal() {
  showRenameModal.value = false
  renameProjectId.value = null
  renameProjectName.value = ''
}


function handleRenameEnter() {
  if (isComposing.value) return
  handleRenameProject()
}


async function handleRenameProject() {
  if (!renameProjectName.value.trim() || !renameProjectId.value) return

  try {
    renaming.value = true
    const updated = await updateProject(renameProjectId.value, {
      name: renameProjectName.value.trim()
    })
    
    const index = projects.value.findIndex(p => p.id === renameProjectId.value)
    if (index !== -1) {
      projects.value[index] = { ...projects.value[index], ...updated }
    }
    closeRenameModal()
  } catch (error) {
    console.error('Failed to rename project:', error)
    notify(t('ui.renameFailed'))
  } finally {
    renaming.value = false
  }
}

function goToProject(projectId: string) {
  router.push(`/project/${projectId}`)
}

const colorMap: Record<ProjectColor, string> = {
  blue: '#3B82F6',
  green: '#22C55E',
  orange: '#F97316',
  red: '#EF4444',
  purple: '#A855F7',
  cyan: '#06B6D4',
  pink: '#EC4899',
  brown: '#A16207'
}


function getProjectColor(color: ProjectColor | null): string {
  return color ? colorMap[color] : '#0b57d0'
}


function formatFileCount(fileCount: number | null | undefined): string {
  if (!Number.isFinite(fileCount)) return t('ui.files')
  return t('ui.fileCount', { count: fileCount })
}


useEscapeClose(() => showCreateModal.value, () => { showCreateModal.value = false })
useEscapeClose(() => showPreflightWarning.value, () => { showPreflightWarning.value = false })
useEscapeClose(() => showRenameModal.value, () => closeRenameModal())

</script>

<style scoped>
.home-page {
  height: 100vh;
  background: var(--bg-main);
  overflow-y: auto;
}

.home-header {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
  background: color-mix(in srgb, var(--bg-main) 86%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.home-main {
  max-width: 1240px;
  margin: 0 auto;
  padding: 40px 24px 80px;
}

/* Hero */
.hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 24px;
  margin-bottom: 40px;
}

.hero-title {
  font-size: clamp(32px, 4.4vw, 48px);
  font-weight: 500;
  line-height: 1.1;
  letter-spacing: -0.025em;
  background: linear-gradient(90deg, #0b57d0 0%, #4285f4 40%, #1aa3a3 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.hero-subtitle {
  margin-top: 12px;
  max-width: 560px;
  font-size: 16px;
  line-height: 1.55;
  color: var(--text-secondary);
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-field {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  width: 260px;
  padding: 0 14px;
  background: var(--bg-white);
  border-radius: var(--radius-full);
  box-shadow: inset 0 0 0 1px var(--border-color);
  color: var(--text-tertiary);
  transition: box-shadow var(--duration-fast);
}

.search-field:focus-within {
  box-shadow: inset 0 0 0 1px var(--primary-color), var(--focus-ring);
}

.search-field input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  font-size: 14px;
  color: var(--text-primary);
}

/* States */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 72px 24px;
  text-align: center;
  background: var(--bg-white);
  border-radius: var(--radius-xl);
}

.empty-state--compact {
  padding: 48px 24px;
}

.empty-state h2 {
  font-size: 22px;
  font-weight: 500;
}

.empty-state p {
  max-width: 420px;
  margin-bottom: 12px;
  color: var(--text-secondary);
}

.empty-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  margin-bottom: 8px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-color);
}

.empty-icon--error {
  background: var(--error-soft);
  color: var(--error-color);
}

/* Groups & grid */
.projects-container {
  display: flex;
  flex-direction: column;
  gap: 36px;
}

.group-title {
  margin-bottom: 14px;
  padding-left: 4px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 16px;
}

/* Cards */
.project-card {
  --card-tint: #e8f0fe;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 196px;
  padding: 20px;
  text-align: left;
  background: var(--card-tint);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition:
    transform var(--duration-base) var(--ease-standard),
    box-shadow var(--duration-base) var(--ease-standard);
}

.project-card:hover,
.project-card:focus-visible {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.project-card.menu-open {
  z-index: 20;
}

.project-card.theme-blue { --card-tint: #e3edfd; }
.project-card.theme-green { --card-tint: #e4f4e8; }
.project-card.theme-orange { --card-tint: #fdeedd; }
.project-card.theme-red { --card-tint: #fce8e6; }
.project-card.theme-purple { --card-tint: #f1e8fd; }
.project-card.theme-cyan { --card-tint: #dff3f7; }
.project-card.theme-pink { --card-tint: #fde7f1; }
.project-card.theme-brown { --card-tint: #f6efd9; }
.project-card.theme-default { --card-tint: #e9eef6; }

.project-card--skeleton {
  background: var(--bg-white);
  cursor: default;
  pointer-events: none;
}

.new-card {
  align-items: center;
  justify-content: center;
  gap: 14px;
  background: var(--bg-white);
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 500;
  box-shadow: inset 0 0 0 1px var(--border-color);
}

.new-card:hover {
  box-shadow: inset 0 0 0 1px var(--primary-color), var(--shadow-md);
}

.new-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-color);
  transition: transform var(--duration-base) var(--ease-emphasized);
}

.new-card:hover .new-icon {
  transform: rotate(90deg);
}

.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.78);
}

.card-title {
  margin-top: auto;
  padding-top: 24px;
  font-size: 18px;
  font-weight: 500;
  line-height: 1.3;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-summary {
  margin-top: 6px;
  min-height: 18px;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.card-menu-wrapper {
  position: absolute;
  top: 12px;
  right: 12px;
}

.card-menu-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
  opacity: 0;
}

.project-card:hover .card-menu-btn,
.project-card:focus-within .card-menu-btn,
.project-card.menu-open .card-menu-btn {
  opacity: 1;
}

.card-menu-btn:hover {
  background: rgba(31, 31, 31, 0.08);
  color: var(--text-primary);
}

.card-dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 100;
  min-width: 190px;
  padding: 8px;
  background: var(--bg-white);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  animation: menu-in var(--duration-base) var(--ease-emphasized);
  transform-origin: top right;
}

@keyframes menu-in {
  from {
    opacity: 0;
    transform: scale(0.94);
  }
}

.card-dropdown-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  text-align: left;
}

.card-dropdown-item svg {
  color: var(--text-tertiary);
}

.card-dropdown-item:hover {
  background: var(--bg-hover);
}

.card-dropdown-item.danger,
.card-dropdown-item.danger svg {
  color: var(--error-color);
}

.card-dropdown-item.danger:hover {
  background: var(--error-soft);
}

/* Dialogs */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.modal {
  width: 100%;
  max-width: 440px;
  padding: 24px;
  background: var(--bg-white);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
}

.modal-title {
  margin-bottom: 18px;
  font-size: 22px;
  font-weight: 500;
}

.modal-input {
  width: 100%;
  height: 48px;
  padding: 0 16px;
  font-size: 15px;
  border-color: var(--border-strong);
  border-radius: var(--radius-md);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 24px;
}

.preflight-desc {
  margin-bottom: 12px;
  color: var(--text-secondary);
}

.preflight-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px 12px 32px;
  background: var(--warning-soft);
  border-radius: var(--radius-md);
  color: var(--warning-color);
  font-size: 13px;
}

@media (max-width: 720px) {
  .home-header {
    padding: 10px 14px;
  }

  .home-main {
    padding: 24px 14px 64px;
  }

  .hero-actions {
    width: 100%;
  }

  .search-field {
    flex: 1;
    width: auto;
  }
}

@media (max-width: 480px) {
  .home-header :deep(.app-logo-text) {
    display: none;
  }
}
</style>
