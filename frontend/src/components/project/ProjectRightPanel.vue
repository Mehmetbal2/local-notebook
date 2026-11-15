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

            <div class="studio-results-scroll">
              <div class="oneclick-queue">
                <div class="queue-header">
                  <span class="queue-title">{{ t('ui.generatedResult') }}</span>
                  <button class="add-note-btn" type="button" @click="emit('add-note')">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
                      <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
                    </svg>
                    {{ t('ui.addNote') }}
                  </button>
                </div>


                <div v-if="features.length > 0" class="result-search">
                  <div class="result-search-box" :class="{ active: resultQuery }">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                    <input
                      v-model="resultQuery"
                      type="search"
                      class="result-search-input"
                      :placeholder="t('ui.searchResultsPlaceholder')"
                      :aria-label="t('ui.searchResultsPlaceholder')"
                      @keydown.esc.prevent="clearResultSearch"
                    />
                    <span v-if="resultSearching" class="result-search-spinner" aria-hidden="true"></span>
                    <button v-if="resultQuery" type="button" class="result-search-clear" :title="t('ui.clearSearch')" @click="clearResultSearch">
                      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                    </button>
                  </div>
                  <div class="result-filter-row">
                    <button
                      type="button"
                      class="result-filter-chip"
                      :class="{ active: resultContent }"
                      :title="t('ui.searchResultContentHint')"
                      :aria-pressed="resultContent"
                      @click="resultContent = !resultContent"
                    >{{ t('ui.searchInContent') }}</button>
                    <span class="result-filter-sep"></span>
                    <button
                      v-for="option in featureKindOptions"
                      :key="option.value"
                      type="button"
                      class="result-filter-chip"
                      :class="{ active: featureKind === option.value }"
                      @click="featureKind = featureKind === option.value ? 'all' : option.value"
                    >{{ option.label }}</button>
                  </div>
                </div>
                <div v-if="features.length === 0" class="queue-empty">
                  <p>{{ hasReadyFiles ? t('ui.useTheButtonsAboveToGenerateQuickTool') : t('ui.uploadSourcesToGenerateQuickTool') }}</p>
                </div>

                <div v-else-if="filteredFeatures.length === 0" class="queue-empty">
                  <p>{{ t('ui.noResultsMatch') }}</p>
                </div>

                <div v-else class="workflow-list">
                  <div
                    v-for="feature in filteredFeatures"
                    :key="feature.id"
                    v-key-activate class="workflow-item feature-item"
                    :class="{ highlighted: highlightedFeatureId === feature.id }"
                    @click="emit('view-feature-detail', feature)"
                  >
                    <div class="workflow-item-icon icon-default" :class="getFeatureSourceClass(feature)">
                      <svg v-bind="getToolIconSvgProps(getFeatureIcon(feature))">
                        <path v-for="(d, idx) in getToolIconDefinition(getFeatureIcon(feature)).paths" :key="idx" :d="d" />
                      </svg>
                    </div>
                    <div class="workflow-item-info">
                      <div class="workflow-item-title-row">
                        <div class="workflow-item-name"><template v-for="(seg, si) in highlight(getFeatureDisplayName(feature), resultWords)" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></div>
                        <span class="workflow-source-chip" :class="getFeatureSourceClass(feature)">
                          {{ getFeatureSourceLabel(feature) }}
                        </span>
                      </div>
                      <div class="workflow-item-status">
                        <span v-if="feature.feature_type !== 'note'" class="workflow-status-badge" :class="getFeatureStatusClass(feature.status)">
                          {{ getFeatureStatusText(feature.status) }}
                        </span>
                        <span v-if="feature.created_at" class="workflow-item-time">{{ formatTime(feature.created_at) }}</span>
                      </div>
                      <div
                        v-if="feature.progress && (feature.status === 'pending' || feature.status === 'processing')"
                        class="feature-progress-line"
                        :title="feature.progress"
                      >{{ feature.progress }}</div>
                      <div v-if="resultSnippet(featureHits, feature.id)" class="result-hit" dir="auto">
                        <template v-for="(seg, si) in resultSnippet(featureHits, feature.id)!" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template>
                        <span v-if="(featureHits.get(feature.id)?.count || 0) > 1" class="result-hit-more">{{ t('ui.moreMatches', { count: (featureHits.get(feature.id)?.count || 0) - 1 }) }}</span>
                      </div>
                    </div>
                    <button
                      v-if="feature.status !== 'pending' && feature.status !== 'processing'"
                      class="workflow-rename-btn"
                      type="button"
                      @click.stop="emit('rename-feature', feature, getFeatureDisplayName(feature))"
                      :title="t('ui.rename')"
                      :aria-label="t('ui.rename')"
                    >
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
                    </button>
                    <button class="workflow-delete-btn" @click.stop="emit('delete-feature', feature)" :title="t('ui.delete')">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
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

            <div class="studio-results-scroll">
              <div class="oneclick-queue">
                <div class="queue-header">
                  <span class="queue-title">{{ t('ui.generatedResult') }}</span>
                </div>


                <div v-if="workflows.length > 0" class="result-search">
                  <div class="result-search-box" :class="{ active: resultQuery }">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
                    <input
                      v-model="resultQuery"
                      type="search"
                      class="result-search-input"
                      :placeholder="t('ui.searchResultsPlaceholder')"
                      :aria-label="t('ui.searchResultsPlaceholder')"
                      @keydown.esc.prevent="clearResultSearch"
                    />
                    <span v-if="resultSearching" class="result-search-spinner" aria-hidden="true"></span>
                    <button v-if="resultQuery" type="button" class="result-search-clear" :title="t('ui.clearSearch')" @click="clearResultSearch">
                      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                    </button>
                  </div>
                  <div class="result-filter-row">
                    <button
                      type="button"
                      class="result-filter-chip"
                      :class="{ active: resultContent }"
                      :title="t('ui.searchResultContentHint')"
                      :aria-pressed="resultContent"
                      @click="resultContent = !resultContent"
                    >{{ t('ui.searchInContent') }}</button>
                  </div>
                </div>
                <div v-if="workflows.length === 0" class="queue-empty">
                  <p>{{ hasReadyFiles ? t('ui.useTheButtonsAboveToGenerateAReport') : t('ui.uploadSourcesToGenerateAReport') }}</p>
                </div>

                <div v-else-if="filteredWorkflows.length === 0" class="queue-empty">
                  <p>{{ t('ui.noResultsMatch') }}</p>
                </div>

                <div v-else class="workflow-list">
                  <div
                    v-for="workflow in filteredWorkflows"
                    :key="workflow.id"
                    v-key-activate class="workflow-item"
                    :class="{ highlighted: highlightedWorkflowId === workflow.id }"
                    @click="emit('view-workflow-detail', workflow.id)"
                  >
                    <div class="workflow-item-icon icon-default" :class="getWorkflowSourceClass(workflow)">
                      <svg v-if="getWorkflowPresetKey(workflow) === 'quick_read'" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                        <path d="M4 4h16v2H4V4zm0 4h10v2H4V8zm0 4h16v2H4v-2zm0 4h10v2H4v-2z"/>
                      </svg>
                      <svg v-else-if="getWorkflowPresetKey(workflow) === 'deep_dive'" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                        <path d="M9 3h6l1 2h4a1 1 0 0 1 1 1v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4l1-2zm1.24 2-.5 1H5v13h14V7h-4.74l-.5-1h-3.52zM7 10h10v2H7v-2zm0 4h7v2H7v-2z"/>
                      </svg>
                      <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
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
                    <div class="workflow-item-info">
                      <div class="workflow-item-title-row">
                        <div class="workflow-item-name"><template v-for="(seg, si) in highlight(getWorkflowDisplayName(workflow), resultWords)" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></div>
                        <span class="workflow-source-chip" :class="getWorkflowSourceClass(workflow)">
                          {{ getWorkflowSourceLabel(workflow) }}
                        </span>
                      </div>
                      <div class="workflow-item-status">
                        <span class="workflow-status-badge" :class="getWorkflowStatusClass(workflow.status)">
                          {{ getWorkflowDisplayStatusText(workflow) }}
                        </span>
                        <span v-if="isWorkflowActiveStatus(workflow.status)" class="workflow-item-time">
                          {{ formatWorkflowProgress(workflow) }}
                        </span>
                        <span v-if="isWorkflowActiveStatus(workflow.status) && workflow.created_at" class="workflow-item-time">
                          {{ formatWorkflowElapsed(workflow.created_at) }}
                        </span>
                        <span v-else-if="workflow.created_at" class="workflow-item-time">{{ formatTime(workflow.created_at) }}</span>
                      </div>
                      <div v-if="resultSnippet(workflowHits, workflow.id)" class="result-hit" dir="auto">
                        <span v-if="workflowHits.get(workflow.id)?.snippets[0]?.section" class="result-hit-section">{{ workflowHits.get(workflow.id)?.snippets[0]?.section }}:</span>
                        <template v-for="(seg, si) in resultSnippet(workflowHits, workflow.id)!" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template>
                        <span v-if="(workflowHits.get(workflow.id)?.count || 0) > 1" class="result-hit-more">{{ t('ui.moreMatches', { count: (workflowHits.get(workflow.id)?.count || 0) - 1 }) }}</span>
                      </div>
                    </div>
                    <button
                      v-if="isWorkflowCancellable(workflow.status)"
                      class="workflow-stop-btn"
                      @click.stop="emit('cancel-workflow', workflow.id)"
                      :title="t('ui.stopGeneration')"
                    >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                        <path d="M6 6h12v12H6z"/>
                      </svg>
                    </button>
                    <button
                      v-if="!isWorkflowCancellable(workflow.status)"
                      class="workflow-rename-btn"
                      type="button"
                      @click.stop="emit('rename-workflow', workflow.id, getWorkflowDisplayName(workflow))"
                      :title="t('ui.rename')"
                      :aria-label="t('ui.rename')"
                    >
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
                    </button>
                    <button v-if="!isWorkflowCancellable(workflow.status)" class="workflow-delete-btn" @click.stop="emit('delete-workflow', workflow.id)" :title="t('ui.delete')">
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </div>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { searchProject, type SearchHit } from '../../services/api'
import { highlight, matchesAll, queryWords, snippetSegments, type TextSegment } from '../../utils/searchText'
import type { FeatureListItem, WebSourceImportResponse, WorkflowDetail, WorkflowListItem, WorkflowContentFeature } from '../../services/api'
import type { Feature, FeatureCitationRefPart } from '../../types'
import { t } from '../../i18n'
import FeatureDetailPanel from './FeatureDetailPanel.vue'
import WorkflowDetailPanel from './WorkflowDetailPanel.vue'
import { TOOL_TYPES, getToolIconDefinition, getToolIconSvgProps } from '../../views/projectPage/toolTypes'
import {
  formatWorkflowProgress,
  getWorkflowDisplayName,
  getWorkflowDisplayStatusText,
  getWorkflowPresetKey,
  getWorkflowSourceClass,
  getWorkflowSourceLabel,
  getWorkflowStatusClass,
  isWorkflowActiveStatus,
  isWorkflowCancellable,
  type WorkflowPresetKey,
} from '../../views/projectPage/workflowHelpers'

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

function getFeatureTool(feature: FeatureListItem): QuickTool | undefined {
  return TOOL_TYPES.find(tool => tool.type === feature.feature_type)
}

function getFeatureDisplayName(feature: FeatureListItem): string {
  return feature.title || feature.display_name || getFeatureSourceLabel(feature)
}

function getFeatureIcon(feature: FeatureListItem): string {
  if (feature.feature_type === 'note') return 'note'
  return getFeatureTool(feature)?.icon || 'summary'
}

function getFeatureSourceLabel(feature: FeatureListItem): string {
  if (feature.feature_type === 'note') {
    return feature.note_source === 'chat' ? t('ui.noteFromChat') : t('ui.note')
  }
  const tool = getFeatureTool(feature)
  return tool ? t(tool.titleKey) : t('ui.quickTools')
}

function getFeatureSourceClass(feature: FeatureListItem): string {
  if (feature.feature_type === 'note') return 'feature-source-note'
  const color = getFeatureTool(feature)?.color || 'cyan'
  return `feature-source-${color}`
}

function getFeatureStatusText(status: FeatureListItem['status']): string {
  if (status === 'pending') return t('ui.queued')
  if (status === 'processing') return t('ui.generating2')
  if (status === 'completed') return t('ui.completed')
  if (status === 'failed') return t('ui.failed')
  return status
}

// ── Search in results, notes and reports ────────────────────────────────────
type FeatureKind = 'all' | 'note' | 'result' | 'deep_research'
const route = useRoute()
const resultQuery = ref('')
const resultContent = ref(false)
const featureKind = ref<FeatureKind>('all')
const featureHits = ref<Map<string, SearchHit>>(new Map())
const workflowHits = ref<Map<string, SearchHit>>(new Map())
const resultSearching = ref(false)
let resultTimer: ReturnType<typeof setTimeout> | null = null
let resultSeq = 0

const featureKindOptions = computed<{ value: FeatureKind; label: string }[]>(() => [
  { value: 'note', label: t('ui.filterNotes') },
  { value: 'result', label: t('ui.filterQuickResults') },
  { value: 'deep_research', label: t('ui.deepResearch') },
])
const resultWords = computed(() => queryWords(resultQuery.value))

function featureKindOf(feature: FeatureListItem): FeatureKind {
  if (feature.feature_type === 'note') return 'note'
  if (feature.feature_type === 'deep_research') return 'deep_research'
  return 'result'
}

const filteredFeatures = computed(() => props.features.filter(feature => {
  if (featureKind.value !== 'all' && featureKindOf(feature) !== featureKind.value) return false
  if (!resultWords.value.length) return true
  return matchesAll(getFeatureDisplayName(feature), resultWords.value) ||
    (resultContent.value && featureHits.value.has(feature.id))
}))

const filteredWorkflows = computed(() => props.workflows.filter(workflow => {
  if (!resultWords.value.length) return true
  return matchesAll(getWorkflowDisplayName(workflow), resultWords.value) ||
    (resultContent.value && workflowHits.value.has(workflow.id))
}))

function resultSnippet(hits: Map<string, SearchHit>, id: string): TextSegment[] | null {
  if (!resultContent.value || !resultWords.value.length) return null
  const snippet = hits.get(id)?.snippets[0]
  return snippet ? snippetSegments(snippet.text, snippet.ranges) : null
}

function clearResultSearch() {
  resultQuery.value = ''
  featureKind.value = 'all'
}

async function runResultSearch() {
  const query = resultQuery.value.trim()
  const projectId = String(route.params.id || '')
  const seq = ++resultSeq
  if (!resultContent.value || query.length < 2 || !projectId) {
    featureHits.value = new Map()
    workflowHits.value = new Map()
    resultSearching.value = false
    return
  }
  resultSearching.value = true
  try {
    const data = await searchProject(projectId, query, 'features')
    if (seq !== resultSeq) return
    const toMap = (hits?: SearchHit[]) => new Map((hits || []).filter(h => h.count > 0).map(h => [h.id, h]))
    featureHits.value = toMap(data.features)
    workflowHits.value = toMap(data.workflows)
  } catch (error) {
    console.error('Result search failed:', error)
  } finally {
    if (seq === resultSeq) resultSearching.value = false
  }
}

watch([resultQuery, resultContent], () => {
  if (resultTimer) clearTimeout(resultTimer)
  resultTimer = setTimeout(runResultSearch, 350)
})

onBeforeUnmount(() => {
  if (resultTimer) clearTimeout(resultTimer)
})

function getFeatureStatusClass(status: FeatureListItem['status']): string {
  if (status === 'pending' || status === 'processing') return 'status-processing'
  if (status === 'completed') return 'status-completed'
  if (status === 'failed') return 'status-failed'
  return ''
}
</script>

<style scoped>
/* The box draws the frame and focus ring; the field inside stays plain. */
.result-search-input,
.result-search-input:focus,
.result-search-input:focus-visible {
  border: none;
  border-radius: 0;
  box-shadow: none;
  outline: none;
  padding: 0;
}

.result-search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: var(--focus-ring);
}

.result-search {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0 0 10px;
}

.result-search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-white);
  color: var(--text-tertiary);
}

.result-search-box:focus-within,
.result-search-box.active {
  border-color: var(--primary-color);
}

.result-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
}

.result-search-input::-webkit-search-cancel-button {
  display: none;
}

.result-search-clear {
  display: flex;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
}

.result-search-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--primary-light);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: result-search-spin 0.8s linear infinite;
}

@keyframes result-search-spin {
  to { transform: rotate(360deg); }
}

.result-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.result-filter-chip {
  padding: 2px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  background: var(--bg-white);
  color: var(--text-secondary);
  font-size: 11.5px;
  cursor: pointer;
}

.result-filter-chip.active {
  border-color: var(--primary-color);
  background: var(--primary-light);
  color: var(--primary-color);
}

.result-filter-sep {
  width: 1px;
  height: 14px;
  background: var(--border-color);
  margin: 0 2px;
}

.search-hit {
  background: #fde68a;
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}

.result-hit {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-hit-section {
  font-weight: 600;
  margin-right: 4px;
}

.result-hit-more {
  margin-left: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
}

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

.oneclick-queue {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
  margin-bottom: 8px;
}

.add-note-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 12px 0 8px;
  border-radius: var(--radius-full);
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--border-strong);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 500;
}

.add-note-btn:hover {
  background: var(--bg-hover);
}

.workflow-item-icon.feature-source-note {
  background: #fdefc3;
  color: #8a5a00;
}

.workflow-source-chip.feature-source-note {
  background: #fdefc3;
  color: #8a5a00;
}

.queue-title {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.queue-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
  line-height: 1.5;
  color: var(--text-tertiary);
  font-size: 13px;
}

.workflow-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s;
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.workflow-item:hover {
  background: var(--bg-hover);
}

.workflow-item.highlighted {
  background: rgba(20, 184, 166, 0.12);
  box-shadow: inset 0 0 0 1px rgba(13, 148, 136, 0.28);
}

.workflow-item-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-right: 12px;
}

.workflow-item-icon.icon-default {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.workflow-item-icon.source-quick-read {
  background: rgba(147, 197, 253, 0.5);
  color: var(--primary-hover);
}

.workflow-item-icon.source-deep-dive {
  background: rgba(199, 210, 254, 0.5);
  color: #4338ca;
}

.workflow-item-icon.source-custom {
  background:
    rgba(20, 184, 166, 0.28),
    radial-gradient(circle at 85% 12%, rgba(255, 255, 255, 0.68) 0%, rgba(255, 255, 255, 0) 34%);
  border: 1px solid rgba(13, 148, 136, 0.28);
  color: #0f766e;
}

.workflow-item-icon.feature-source-cyan {
  background: rgba(165, 243, 252, 0.5);
  color: #0e7490;
}

.workflow-item-icon.feature-source-amber {
  background: rgba(253, 230, 138, 0.5);
  color: #b45309;
}

.workflow-item-icon.feature-source-indigo {
  background: rgba(199, 210, 254, 0.5);
  color: #4338ca;
}

.workflow-item-icon.feature-source-green {
  background: rgba(187, 247, 208, 0.55);
  color: #15803d;
}

.workflow-item-icon.feature-source-teal {
  background: rgba(153, 246, 228, 0.5);
  color: #0f766e;
}

.workflow-item-icon.feature-source-purple {
  background: rgba(233, 213, 255, 0.55);
  color: #7e22ce;
}

.workflow-item-icon.feature-source-rose {
  background: rgba(254, 205, 211, 0.55);
  color: #be123c;
}

.workflow-item-icon.feature-source-blue {
  background: rgba(147, 197, 253, 0.5);
  color: var(--primary-hover);
}

.workflow-item-icon.feature-source-orange {
  background: rgba(254, 215, 170, 0.6);
  color: #c2410c;
}

.workflow-item-icon.feature-source-custom {
  background:
    rgba(20, 184, 166, 0.28),
    radial-gradient(circle at 85% 12%, rgba(255, 255, 255, 0.68) 0%, rgba(255, 255, 255, 0) 34%);
  border: 1px solid rgba(13, 148, 136, 0.28);
  color: #0f766e;
}

.workflow-item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.workflow-item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.workflow-item-name {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.35;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-source-chip {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  height: 18px;
  max-width: 118px;
  padding: 0 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 650;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-source-chip.source-quick-read {
  background: rgba(147, 197, 253, 0.42);
  color: var(--primary-hover);
}

.workflow-source-chip.source-deep-dive {
  background: rgba(199, 210, 254, 0.55);
  color: #4338ca;
}

.workflow-source-chip.source-custom {
  background:
    rgba(20, 184, 166, 0.2),
    radial-gradient(circle at 86% 12%, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0) 36%);
  border: 1px solid rgba(13, 148, 136, 0.22);
  color: #0f766e;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  letter-spacing: 0;
}

.workflow-source-chip.feature-source-cyan {
  background: rgba(165, 243, 252, 0.44);
  color: #0e7490;
}

.workflow-source-chip.feature-source-amber {
  background: rgba(253, 230, 138, 0.5);
  color: #b45309;
}

.workflow-source-chip.feature-source-indigo {
  background: rgba(199, 210, 254, 0.55);
  color: #4338ca;
}

.workflow-source-chip.feature-source-green {
  background: rgba(187, 247, 208, 0.55);
  color: #15803d;
}

.workflow-source-chip.feature-source-teal {
  background: rgba(153, 246, 228, 0.52);
  color: #0f766e;
}

.workflow-source-chip.feature-source-purple {
  background: rgba(233, 213, 255, 0.58);
  color: #7e22ce;
}

.workflow-source-chip.feature-source-rose {
  background: rgba(254, 205, 211, 0.58);
  color: #be123c;
}

.workflow-source-chip.feature-source-blue {
  background: rgba(147, 197, 253, 0.42);
  color: var(--primary-hover);
}

.workflow-source-chip.feature-source-orange {
  background: rgba(254, 215, 170, 0.58);
  color: #c2410c;
}

.workflow-source-chip.feature-source-custom {
  background:
    rgba(20, 184, 166, 0.2),
    radial-gradient(circle at 86% 12%, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0) 36%);
  border: 1px solid rgba(13, 148, 136, 0.22);
  color: #0f766e;
}

.workflow-item-time {
  font-size: 12px;
  color: var(--text-tertiary);
}

.workflow-item-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workflow-status-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.feature-progress-line {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-status-badge.status-pending {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.workflow-status-badge.status-processing {
  background: rgba(59, 130, 246, 0.15);
  color: var(--primary-color);
  position: relative;
  animation: workflowBreathing 1.6s ease-in-out infinite;
}

.workflow-status-badge.status-cancelling {
  background: rgba(245, 158, 11, 0.15);
  color: #d97706;
  position: relative;
}

.workflow-status-badge.status-completed {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.workflow-status-badge.status-failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--error-color);
}

.workflow-status-badge.status-partial {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.workflow-status-badge.status-cancelled {
  background: rgba(107, 114, 128, 0.15);
  color: var(--text-tertiary);
}

.workflow-status-badge.status-processing::after,
.workflow-status-badge.status-cancelling::after {
  content: '...';
  display: inline-block;
  margin-left: 2px;
  animation: workflowDots 1.2s steps(4, end) infinite;
}

@keyframes workflowDots {
  0% { clip-path: inset(0 100% 0 0); }
  33% { clip-path: inset(0 66% 0 0); }
  66% { clip-path: inset(0 33% 0 0); }
  100% { clip-path: inset(0 0 0 0); }
}

@keyframes workflowBreathing {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.25);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(59, 130, 246, 0);
  }
}

.workflow-stop-btn,
.workflow-delete-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 8px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.workflow-rename-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-left: 8px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.workflow-rename-btn + .workflow-delete-btn {
  margin-left: 2px;
}

.workflow-rename-btn:hover {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.workflow-item:hover .workflow-stop-btn,
.workflow-item:hover .workflow-rename-btn,
.workflow-item:hover .workflow-delete-btn,
.workflow-item:focus-within .workflow-rename-btn,
.workflow-item:focus-within .workflow-delete-btn {
  opacity: 1;
}

@media (hover: none) {
  .workflow-rename-btn,
  .workflow-delete-btn {
    opacity: 1;
  }
}

.workflow-stop-btn {
  opacity: 1;
}

.workflow-stop-btn:hover {
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.workflow-delete-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--error-color);
}
</style>
