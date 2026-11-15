<template>
  <div v-if="rightPanelCollapsed" class="collapsed-sidebar right">
    <div v-key-activate class="collapsed-icon-btn" @click="emit('update:rightPanelCollapsed', false)" :title="$t('ui.expandToolboxPanel')">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z"/>
        <path d="M13 7h4v10h-4z" opacity="0.5"/>
      </svg>
    </div>
    <div
      v-for="tool in enabledQuickTools"
      :key="tool.type"
      v-key-activate class="collapsed-icon-btn"
      :class="{ disabled: !hasReadyFiles }"
      :title="hasReadyFiles ? t(tool.titleKey) : `${t(tool.titleKey)} (${t('ui.uploadAndProcessFilesFirst')})`"
      @click="handleCollapsedToolClick(tool)"
    >
      <svg v-bind="getToolIconSvgProps(tool.icon)">
        <path v-for="(d, idx) in getToolIconDefinition(tool.icon).paths" :key="idx" :d="d" />
      </svg>
    </div>
    <div
      v-key-activate class="collapsed-icon-btn"
      @click="handleCollapsedReportsClick"
      :title="$t('ui.smartAnalysis')"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path d="M9 3h6l1 2h4a1 1 0 0 1 1 1v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4l1-2zm1.24 2-.5 1H5v13h14V7h-4.74l-.5-1h-3.52zM7 10h10v2H7v-2zm0 4h7v2H7v-2z"/>
      </svg>
    </div>
  </div>

  <aside
    class="studio-panel"
    :class="{ collapsed: rightPanelCollapsed, 'detail-mode': showFeatureDetail || showWorkflowDetail }"
    :style="{
      width: rightPanelCollapsed ? '0px' : `${rightPanelWidth}px`,
      maxWidth: (showFeatureDetail || showWorkflowDetail) ? '900px' : '600px'
    }"
  >
    <WorkflowDetailPanel
      v-if="showWorkflowDetail && currentWorkflow"
      :key="currentWorkflow.id"
      :workflow="currentWorkflow"
      :features="workflowFeatures"
      :active-citation-num="activeWorkflowCitationNum"
      :active-feature-id="activeWorkflowFeatureId"
      @close="emit('close-workflow-detail')"
      @cancel="workflowId => emit('cancel-workflow', workflowId)"
      @update-title="(id, title) => emit('workflow-title-update', id, title)"
      @citation-click="(part, feature) => emit('workflow-citation-click', part, feature)"
      @clear-citation="emit('clear-workflow-citation')"
      @regenerate-step="stepIndex => emit('workflow-step-regenerate', stepIndex)"
      @show-toast="(message, type) => emit('show-toast', message, type)"
    />

    <FeatureDetailPanel
      v-else-if="showFeatureDetail && activeFeature"
      :feature="activeFeature"
      :active-citation-num="activeFeatureCitationNum"
      @close="emit('close-feature-detail')"
      @citation-click="part => emit('feature-citation-click', part)"
      @clear-citation="emit('clear-feature-citation')"
      @rename="title => emit('feature-rename', title)"
      @regenerate="emit('feature-regenerate')"
      @edit-note="emit('feature-edit-note')"
      @ask-in-chat="payload => emit('ask-in-chat', payload)"
      @sources-imported="result => emit('web-imported', result)"
    />

    <template v-else>
      <div class="panel-header">
        <div class="panel-title-wrapper" role="tablist">
          <button
            v-for="tab in toolboxTabs"
            :key="tab.mode"
            class="panel-title"
            :class="{ active: toolboxMode === tab.mode }"
            type="button"
            role="tab"
            :aria-selected="toolboxMode === tab.mode"
            :title="tab.tooltipKey ? t(tab.tooltipKey) : undefined"
            @click="emit('update:toolboxMode', tab.mode)"
          >{{ t(tab.labelKey) }}</button>
        </div>
        <button class="panel-toggle-btn" @click="emit('update:rightPanelCollapsed', true)" :title="$t('ui.collapsePanel')">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z"/>
            <path d="M13 7h4v10h-4z" opacity="0.5"/>
          </svg>
        </button>
      </div>

      <div class="studio-content-wrapper">
        <Transition :name="transitionName">
          <div v-if="toolboxMode !== 'oneclick'" class="studio-content" :key="toolboxMode">
            <div class="studio-tools-fixed">
              <div class="tool-grid oneclick">
                <div
                  v-for="tool in visibleQuickTools"
                  :key="tool.type"
                  v-key-activate class="tool-card"
                  :class="[`tool-card--${tool.color}`, { disabled: !hasReadyFiles }]"
                  :title="hasReadyFiles ? t(tool.tooltipKey) : t('ui.uploadAndProcessFilesFirst')"
                  @click="hasReadyFiles && emit('open-tool-config', tool)"
                >
                  <div class="tool-card-icon">
                    <svg v-bind="getToolIconSvgProps(tool.icon)">
                      <path v-for="(d, idx) in getToolIconDefinition(tool.icon).paths" :key="idx" :d="d" />
                    </svg>
                  </div>
                  <span class="tool-card-title">{{ t(tool.titleKey) }}</span>
                </div>
              </div>
            </div>

            <ResultsList
              :mode="toolboxMode"
              :features="features"
              :workflows="workflows"
              :has-ready-files="hasReadyFiles"
              :highlighted-feature-id="highlightedFeatureId"
              :highlighted-workflow-id="highlightedWorkflowId"
              :format-time="formatTime"
              :format-workflow-elapsed="formatWorkflowElapsed"
              @add-note="emit('add-note')"
              @view-feature-detail="emit('view-feature-detail', $event)"
              @rename-feature="(feature, name) => emit('rename-feature', feature, name)"
              @delete-feature="emit('delete-feature', $event)"
              @view-workflow-detail="emit('view-workflow-detail', $event)"
              @cancel-workflow="emit('cancel-workflow', $event)"
              @rename-workflow="(id, name) => emit('rename-workflow', id, name)"
              @delete-workflow="emit('delete-workflow', $event)"
            />
          </div>

          <div v-else class="studio-content" key="oneclick">
            <div class="studio-tools-fixed">
              <div class="tool-grid oneclick">
                <div class="tool-card tool-card--blue" :class="{ disabled: !hasReadyFiles }" :title="hasReadyFiles ? t('ui.quicklyGraspTheMainThreadAndKeyPoints') : t('ui.uploadAndProcessFilesFirst')" @click="openWorkflowConfig('quick_read')">
                  <div class="tool-card-icon">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M4 4h16v2H4V4zm0 4h10v2H4V8zm0 4h16v2H4v-2zm0 4h10v2H4v-2z"/></svg>
                  </div>
                  <span class="tool-card-title">{{ t('ui.quickRead') }}</span>
                </div>
                <div class="tool-card tool-card--indigo" :class="{ disabled: !hasReadyFiles }" :title="hasReadyFiles ? t('ui.systematicallyUnpackTheKeyLogicInTheMaterial') : t('ui.uploadAndProcessFilesFirst')" @click="openWorkflowConfig('deep_dive')">
                  <div class="tool-card-icon">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M9 3h6l1 2h4a1 1 0 0 1 1 1v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4l1-2zm1.24 2-.5 1H5v13h14V7h-4.74l-.5-1h-3.52zM7 10h10v2H7v-2zm0 4h7v2H7v-2z"/></svg>
                  </div>
                  <span class="tool-card-title">{{ t('ui.coreDeepDive') }}</span>
                </div>
                <div class="tool-card tool-card--custom" :class="{ disabled: !hasReadyFiles }" :title="hasReadyFiles ? t('ui.planAndGenerateFullyFromYourInstructions') : t('ui.uploadAndProcessFilesFirst')" @click="openWorkflowConfig('custom')">
                  <div class="tool-card-icon">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M4 21v-7"/>
                      <path d="M4 10V3"/>
                      <path d="M12 21v-9"/>
                      <path d="M12 8V3"/>
                      <path d="M20 21v-5"/>
                      <path d="M20 12V3"/>
                      <path d="M2 14h4"/>
                      <path d="M10 8h4"/>
                      <path d="M18 16h4"/>
                    </svg>
                  </div>
                  <span class="tool-card-title">{{ t('ui.customWorkflow') }}</span>
                </div>
              </div>
            </div>

            <ResultsList
              mode="oneclick"
              :features="features"
              :workflows="workflows"
              :has-ready-files="hasReadyFiles"
              :highlighted-feature-id="highlightedFeatureId"
              :highlighted-workflow-id="highlightedWorkflowId"
              :format-time="formatTime"
              :format-workflow-elapsed="formatWorkflowElapsed"
              @add-note="emit('add-note')"
              @view-feature-detail="emit('view-feature-detail', $event)"
              @rename-feature="(feature, name) => emit('rename-feature', feature, name)"
              @delete-feature="emit('delete-feature', $event)"
              @view-workflow-detail="emit('view-workflow-detail', $event)"
              @cancel-workflow="emit('cancel-workflow', $event)"
              @rename-workflow="(id, name) => emit('rename-workflow', id, name)"
              @delete-workflow="emit('delete-workflow', $event)"
            />
          </div>
        </Transition>
      </div>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FeatureListItem, WebSourceImportResponse, WorkflowDetail, WorkflowListItem, WorkflowContentFeature } from '../../services/api'
import type { Feature, FeatureCitationRefPart } from '../../types'
import { t } from '../../i18n'
import FeatureDetailPanel from './FeatureDetailPanel.vue'
import WorkflowDetailPanel from './WorkflowDetailPanel.vue'
import ResultsList from './ResultsList.vue'
import { TOOL_TYPES, getToolIconDefinition, getToolIconSvgProps } from '../../views/projectPage/toolTypes'
import type { WorkflowPresetKey } from '../../views/projectPage/workflowHelpers'

/** 'tools' is the learning tab (kept for saved preferences), 'analysis' the analysis tab. */
type ToolboxMode = 'tools' | 'analysis' | 'oneclick'
type ToastType = 'success' | 'error' | 'info' | 'warning'
type QuickTool = typeof TOOL_TYPES[number]

const enabledQuickTools = TOOL_TYPES.filter(tool => tool.enabled && !tool.type.includes('image') && !tool.type.includes('video'))

const toolboxTabs: Array<{ mode: ToolboxMode; labelKey: string; tooltipKey?: string }> = [
  { mode: 'tools', labelKey: 'ui.learningTools', tooltipKey: 'ui.learningToolsTooltip' },
  { mode: 'analysis', labelKey: 'ui.analysisTools', tooltipKey: 'ui.analysisToolsTooltip' },
  { mode: 'oneclick', labelKey: 'ui.smartAnalysis' },
]

function modeForTool(tool: QuickTool): ToolboxMode {
  return tool.category === 'analyze' ? 'analysis' : 'tools'
}

const props = defineProps<{
  rightPanelCollapsed: boolean
  rightPanelWidth: number
  showFeatureDetail: boolean
  showWorkflowDetail: boolean
  currentWorkflow: WorkflowDetail | null
  workflowFeatures: WorkflowContentFeature[]
  activeWorkflowCitationNum: number | null
  activeWorkflowFeatureId: string | null
  activeFeature: Feature | null
  activeFeatureCitationNum: number | null
  toolboxMode: ToolboxMode
  transitionName: string
  hasReadyFiles: boolean
  features: FeatureListItem[]
  workflows: WorkflowListItem[]
  highlightedFeatureId: string | null
  highlightedWorkflowId: string | null
  formatTime: (isoString: string) => string
  formatWorkflowElapsed: (isoString: string) => string
}>()

const emit = defineEmits<{
  (e: 'update:rightPanelCollapsed', value: boolean): void
  (e: 'update:toolboxMode', value: ToolboxMode): void
  (e: 'close-workflow-detail'): void
  (e: 'cancel-workflow', workflowId: string): void
  (e: 'delete-workflow', workflowId: string): void
  (e: 'rename-workflow', workflowId: string, currentName: string): void
  (e: 'workflow-title-update', id: string, title: string): void
  (e: 'workflow-citation-click', part: FeatureCitationRefPart, feature: WorkflowContentFeature): void
  (e: 'clear-workflow-citation'): void
  (e: 'workflow-step-regenerate', stepIndex: number): void
  (e: 'show-toast', message: string, type: ToastType): void
  (e: 'close-feature-detail'): void
  (e: 'feature-citation-click', part: FeatureCitationRefPart): void
  (e: 'clear-feature-citation'): void
  (e: 'feature-rename', newTitle: string): void
  (e: 'feature-regenerate'): void
  (e: 'feature-edit-note'): void
  (e: 'add-note'): void
  (e: 'web-imported', result: WebSourceImportResponse): void
  (e: 'ask-in-chat', payload: { topic: string; context: string }): void
  (e: 'open-tool-config', tool: QuickTool): void
  (e: 'view-feature-detail', feature: FeatureListItem): void
  (e: 'delete-feature', feature: FeatureListItem): void
  (e: 'rename-feature', feature: FeatureListItem, currentName: string): void
  (e: 'open-workflow-config', presetKey: WorkflowPresetKey): void
  (e: 'view-workflow-detail', workflowId: string): void
}>()

function openWorkflowConfig(presetKey: WorkflowPresetKey) {
  emit('open-workflow-config', presetKey)
}

const visibleQuickTools = computed(() =>
  enabledQuickTools.filter(tool => modeForTool(tool) === props.toolboxMode)
)

function handleCollapsedToolClick(tool: QuickTool) {
  emit('update:toolboxMode', modeForTool(tool))
  emit('update:rightPanelCollapsed', false)
  if (props.hasReadyFiles) {
    emit('open-tool-config', tool)
  }
}

function handleCollapsedReportsClick() {
  emit('update:toolboxMode', 'oneclick')
  emit('update:rightPanelCollapsed', false)
}
</script>

<style scoped>
.collapsed-sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  margin-left: 12px;
  background: var(--bg-white);
  border-radius: var(--radius-lg);
  flex-shrink: 0;
}

.collapsed-icon-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: 10px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  position: relative;
}

.collapsed-icon-btn:hover:not(.disabled) {
  background: var(--bg-hover);
  color: var(--primary-color);
}

.collapsed-icon-btn.disabled {
  color: var(--text-tertiary);
  opacity: 0.6;
  cursor: not-allowed;
}

.studio-panel {
  background: var(--bg-white);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  flex-shrink: 1;
  overflow: hidden;
  transition: width 0.2s ease;
  min-width: 280px;
  max-width: 500px;
}

.studio-panel.collapsed {
  padding: 0;
  border: none;
  overflow: hidden;
  min-width: 0;
}

.studio-panel.collapsed > * {
  display: none;
}

.panel-header {
  min-height: 52px;
  padding: 10px 12px 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  overflow: visible;
  position: relative;
  z-index: 10;
  border-bottom: 1px solid var(--border-light);
}

.panel-toggle-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 50%;
  color: var(--text-tertiary);
  cursor: pointer;
}

.panel-toggle-btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.studio-content-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.studio-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 16px 16px;
  overflow: hidden;
  min-height: 0;
  width: 100%;
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: var(--bg-white);
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.3s ease-out;
}

.slide-left-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.slide-left-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 0.3s ease-out;
}

.slide-right-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}

.slide-right-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.studio-tools-fixed {
  flex-shrink: 0;
  max-height: 46%;
  overflow-y: auto;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.studio-results-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.studio-results-scroll::-webkit-scrollbar {
  width: 6px;
}

.studio-results-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.studio-results-scroll::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 3px;
  transition: background 0.2s;
}

.studio-results-scroll:hover::-webkit-scrollbar-thumb {
  background: var(--border-color);
}

.studio-results-scroll:hover::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

.panel-title-wrapper {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
}

.panel-title-wrapper .panel-title {
  border: none;
  background: transparent;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 5px 14px;
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
  user-select: none;
  white-space: nowrap;
}

.panel-title-wrapper .panel-title:hover {
  color: var(--text-secondary);
}

.panel-title-wrapper .panel-title.active {
  background: var(--bg-white);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.panel-title-wrapper .panel-title-divider {
  display: none;
}

.tool-grid.oneclick {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.tool-grid.oneclick .tool-card {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: transform 0.2s var(--ease-standard), box-shadow 0.2s var(--ease-standard), filter 0.2s;
  min-height: 76px;
}

.tool-grid.oneclick .tool-card:hover:not(.disabled):not(.tool-card--placeholder) {
  transform: translateY(-1px);
  filter: saturate(1.25) brightness(0.98);
  box-shadow: var(--shadow-sm);
}

.tool-grid.oneclick .tool-card.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.tool-grid.oneclick .tool-card-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}

.tool-grid.oneclick .tool-card-title {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.2;
}

.tool-card--blue {
  background: rgba(147, 197, 253, 0.5);
}

.tool-card--blue .tool-card-icon,
.tool-card--blue .tool-card-title {
  color: var(--primary-hover);
}

.tool-card--cyan {
  background: rgba(165, 243, 252, 0.5);
}

.tool-card--cyan .tool-card-icon,
.tool-card--cyan .tool-card-title {
  color: #0e7490;
}

.tool-card--amber {
  background: rgba(253, 230, 138, 0.5);
}

.tool-card--amber .tool-card-icon,
.tool-card--amber .tool-card-title {
  color: #b45309;
}

.tool-card--indigo {
  background: rgba(199, 210, 254, 0.5);
}

.tool-card--indigo .tool-card-icon,
.tool-card--indigo .tool-card-title {
  color: #4338ca;
}

.tool-card--green {
  background: rgba(187, 247, 208, 0.55);
}

.tool-card--green .tool-card-icon,
.tool-card--green .tool-card-title {
  color: #15803d;
}

.tool-card--teal {
  background: rgba(153, 246, 228, 0.5);
}

.tool-card--teal .tool-card-icon,
.tool-card--teal .tool-card-title {
  color: #0f766e;
}

.tool-card--purple {
  background: rgba(233, 213, 255, 0.55);
}

.tool-card--purple .tool-card-icon,
.tool-card--purple .tool-card-title {
  color: #7e22ce;
}

.tool-card--rose {
  background: rgba(254, 205, 211, 0.55);
}

.tool-card--rose .tool-card-icon,
.tool-card--rose .tool-card-title {
  color: #be123c;
}

.tool-card--orange {
  background: rgba(254, 215, 170, 0.6);
}

.tool-card--orange .tool-card-icon,
.tool-card--orange .tool-card-title {
  color: #c2410c;
}

.tool-card--custom {
  background:
    rgba(20, 184, 166, 0.28),
    radial-gradient(circle at 85% 12%, rgba(255, 255, 255, 0.68) 0%, rgba(255, 255, 255, 0) 34%);
  border: 1px solid rgba(13, 148, 136, 0.28);
}

.tool-grid.oneclick .tool-card--custom {
  min-height: 54px;
  padding: 9px 12px;
}

.tool-grid.oneclick .tool-card--custom .tool-card-icon {
  margin-bottom: 4px;
}

.tool-card--custom .tool-card-icon {
  color: #0f766e;
}

.tool-card--custom .tool-card-title {
  color: #0f766e;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-weight: 650;
  letter-spacing: 0;
}

.tool-grid.oneclick .tool-card--custom:hover:not(.disabled) {
  box-shadow: 0 6px 16px rgba(13, 148, 136, 0.18);
}

</style>
