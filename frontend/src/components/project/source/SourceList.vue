<template>
  <div class="panel-header">
    <span class="panel-title">{{ $t('ui.sources2') }}</span>
    <div class="panel-header-actions">
      <button
        v-if="files.length > 0"
        type="button"
        class="panel-toggle-btn"
        :class="{ active: manageMode }"
        :aria-pressed="manageMode"
        :title="manageMode ? $t('ui.doneManagingSources') : $t('ui.manageSources')"
        :aria-label="manageMode ? $t('ui.doneManagingSources') : $t('ui.manageSources')"
        @click="toggleManageMode"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
          <path d="M3 5h2v2H3V5zm4 0h14v2H7V5zM3 11h2v2H3v-2zm4 0h14v2H7v-2zm-4 6h2v2H3v-2zm4 0h14v2H7v-2z"/>
        </svg>
      </button>
    <button class="panel-toggle-btn" @click="emit('toggle-collapse')" :title="$t('ui.collapsePanel')">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z"/>
        <path d="M7 7h4v10H7z" opacity="0.5"/>
      </svg>
    </button>
    </div>
  </div>

  <button class="add-source-btn" @click="emit('trigger-file-upload')">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
      <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" />
    </svg>
    {{ $t('ui.addSource') }}
  </button>

  <div v-if="files.length > 0" class="source-search">
    <div class="source-search-box" :class="{ active: searchQuery }">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
      <input
        v-model="searchQuery"
        type="search"
        class="source-search-input"
        :placeholder="$t('ui.searchSourcesPlaceholder')"
        :aria-label="$t('ui.searchSourcesPlaceholder')"
        @keydown.esc.prevent="clearSearch"
      />
      <button v-if="searchQuery" type="button" class="source-search-clear" :title="$t('ui.clearSearch')" @click="clearSearch">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div class="source-filter-row">
      <button
        type="button"
        class="source-filter-chip"
        :class="{ active: searchContent }"
        :title="$t('ui.searchInContentHint')"
        :aria-pressed="searchContent"
        @click="searchContent = !searchContent"
      >
        <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
        {{ $t('ui.searchInContent') }}
      </button>
      <span class="source-filter-sep"></span>
      <button
        v-for="option in filterOptions"
        :key="option.value"
        type="button"
        class="source-filter-chip"
        :class="{ active: sourceFilter === option.value }"
        @click="sourceFilter = sourceFilter === option.value ? 'all' : option.value"
      >{{ option.label }}</button>
    </div>
    <div v-if="isFiltering" class="source-search-result" role="status">
      <span v-if="contentSearching" class="source-search-spinner" aria-hidden="true"></span>
      <span class="source-search-count">{{ $t('ui.sourcesFoundCount', { count: visibleFiles.length, total: files.length }) }}</span>
      <template v-if="visibleReadyIds.length > 0">
        <button type="button" class="source-search-action" @click="emit('set-file-selection', visibleReadyIds, 'add')">{{ $t('ui.selectFound') }}</button>
        <button type="button" class="source-search-action" @click="emit('set-file-selection', visibleReadyIds, 'only')">{{ $t('ui.selectOnlyFound') }}</button>
      </template>
    </div>
    <p v-if="contentError" class="source-search-error">{{ contentError }}</p>
  </div>

  <div v-if="uploadingFiles.length > 0" class="upload-progress-container">
    <div
      v-for="(item, index) in uploadingFiles"
      :key="index"
      class="upload-progress-item"
      :class="item.status"
    >
      <div class="upload-file-name">{{ item.name }}</div>
      <div class="upload-progress-bar">
        <div
          class="upload-progress-fill"
          :style="{ width: item.progress + '%' }"
        ></div>
      </div>
      <div class="upload-status">
        <template v-if="item.status === 'uploading'">{{ item.progress }}%</template>
        <template v-else-if="item.status === 'success'">{{ $t('ui.done') }}</template>
        <template v-else-if="item.status === 'error'">{{ $t('ui.failed') }}</template>
      </div>
    </div>
  </div>

  <div v-if="manageMode" class="manage-bar" role="toolbar" :aria-label="$t('ui.manageSources')">
    <div v-key-activate class="manage-select-row" @click="toggleManageAll">
      <span>{{ managedIds.size > 0 ? $t('ui.sourcesSelectedCount', { count: managedIds.size }) : $t('ui.selectSourcesToManage') }}</span>
      <div class="select-all-check" :class="{ checked: allManaged, partial: someManaged }">
        <svg v-if="allManaged" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
        <span v-else-if="someManaged" class="partial-mark" aria-hidden="true"></span>
      </div>
    </div>
    <div class="manage-actions">
      <button v-if="managedRestartableIds.length > 0" type="button" class="manage-action" @click="emit('reprocess-files', managedRestartableIds)">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
        {{ $t('ui.restartProcessing') }} ({{ managedRestartableIds.length }})
      </button>
      <button v-if="managedActiveIds.length > 0 || managedRestartableIds.length === 0" type="button" class="manage-action" :disabled="managedActiveIds.length === 0" @click="emit('cancel-files', managedActiveIds)">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4 14H8V8h8v8z"/></svg>
        {{ $t('ui.stopProcessing') }}<template v-if="managedActiveIds.length > 0"> ({{ managedActiveIds.length }})</template>
      </button>
      <button type="button" class="manage-action" :disabled="managedReadyIds.length === 0" @click="emit('suggest-names', managedReadyIds)">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/></svg>
        {{ $t('ui.sourceNamingSuggest') }}
      </button>
      <button type="button" class="manage-action danger" :disabled="managedIds.size === 0" @click="emit('delete-files', Array.from(managedIds))">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
        {{ $t('ui.delete') }}<template v-if="managedIds.size > 0"> ({{ managedIds.size }})</template>
      </button>
      <button type="button" class="manage-action done" @click="exitManageMode">{{ $t('ui.manageDone') }}</button>
    </div>
  </div>

  <div v-if="!manageMode && namingFileIds.length > 0" class="naming-banner" role="status">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" class="naming-banner-icon" aria-hidden="true"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/></svg>
    <span class="naming-banner-text">{{ $t('ui.sourceNamingBanner', { count: namingFileIds.length }) }}</span>
    <button type="button" class="naming-banner-action" @click="emit('suggest-names', namingFileIds)">{{ $t('ui.sourceNamingSuggest') }}</button>
    <button type="button" class="naming-banner-close" :title="$t('ui.sourceNamingDismiss')" :aria-label="$t('ui.sourceNamingDismiss')" @click="emit('dismiss-naming', namingFileIds)">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
    </button>
  </div>

  <div v-if="!manageMode && activeFileIds.length > 1" class="processing-summary">
    <span>{{ $t('ui.filesProcessingCount', { count: activeFileIds.length }) }}</span>
    <button type="button" class="processing-stop-all" @click="emit('cancel-files', activeFileIds)">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4 14H8V8h8v8z"/></svg>
      {{ $t('ui.stopAllProcessing') }}
    </button>
  </div>

  <div v-if="!manageMode && restartableFileIds.length > 1" class="processing-summary stopped-summary">
    <span>{{ $t('ui.filesStoppedCount', { count: restartableFileIds.length }) }}</span>
    <button type="button" class="processing-stop-all restart-all" @click="emit('reprocess-files', restartableFileIds)">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
      {{ $t('ui.restartAllProcessing') }}
    </button>
  </div>

  <div v-if="!manageMode && readyFiles.length > 0" v-key-activate class="select-all-row" @click="emit('toggle-select-all')">
    <span>{{ $t('ui.selectAllSources') }}</span>
    <div class="select-all-check" :class="{ checked: isAllSelected }">
      <svg v-if="isAllSelected" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
      </svg>
    </div>
  </div>

  <div class="sources-list">
    <div v-if="files.length === 0" class="empty-sources">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
          <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
        </svg>
      </div>
      <p>{{ $t('ui.savedSourcesWillAppearHere') }}</p>
      <p class="hint">{{ $t('ui.clickAddSourceAboveToAddPdfOr') }}</p>
    </div>

    <div v-if="files.length > 0 && isFiltering && visibleFiles.length === 0 && !contentSearching" class="source-search-empty">
      {{ $t('ui.noSourcesMatch') }}
    </div>

    <template v-for="file in visibleFiles" :key="file.id">
    <div
      v-key-activate class="source-item"
      :class="{
        selected: selectedFileIds.includes(file.id),
        processing: file.status === 'processing',
        pending: file.status === 'pending',
        ready: file.status === 'ready',
        stopped: file.status === 'cancelled',
        managing: manageMode,
        managed: manageMode && managedIds.has(file.id)
      }"
      @click="onRowClick(file)"
      @mouseenter="emit('set-hovering-file', file.id)"
      @mouseleave="emit('set-hovering-file', null)"
    >
      <div class="source-left">
        <div v-if="!manageMode && (hoveringFileId === file.id || openMenuFileId === file.id)" class="source-menu-wrapper">
          <button
            class="source-menu-btn"
            @click.stop="emit('toggle-file-menu', file.id)"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
            </svg>
          </button>

          <div v-if="openMenuFileId === file.id" class="source-dropdown">
            <button v-if="file.status === 'ready'" class="dropdown-item" @click.stop="emit('rename-file', file.id, file.file_name)">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
              </svg>
              {{ $t('ui.rename') }}
            </button>
            <button v-if="file.status === 'ready'" class="dropdown-item" @click.stop="emit('suggest-names', [file.id])">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/></svg>
              {{ $t('ui.sourceNamingMenu') }}
            </button>
            <button v-if="isActive(file)" class="dropdown-item" @click.stop="emit('cancel-files', [file.id])">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4 14H8V8h8v8z"/></svg>
              {{ $t('ui.stopProcessing') }}
            </button>
            <button v-if="isRestartable(file)" class="dropdown-item" @click.stop="emit('reprocess-files', [file.id])">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
              {{ $t('ui.reprocessFile') }}
            </button>
            <button class="dropdown-item danger" @click.stop="emit('delete-file', file.id)">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
              </svg>
              {{ $t('ui.delete') }}
            </button>
          </div>
        </div>

        <div v-else class="source-icon" :class="{ 'image-icon': isImageFile(file), 'audio-icon': isAudioFile(file) }">
          <svg v-if="isImageFile(file)" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
          </svg>

          <svg v-else-if="isAudioFile(file)" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
          </svg>

          <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
          </svg>
        </div>
      </div>

      <div class="source-info">
        <span class="source-name"><template v-for="(seg, si) in nameSegments(file)" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></span>
        <span
          v-if="file.status !== 'ready'"
          class="source-status"
          :class="file.status"
          :title="file.status === 'failed' ? (file.error_message || '') : ''"
        >
          {{ getSourceStatusText(file) }}
          <span v-if="file.status === 'failed' && file.error_message" class="source-status-reason">
            {{ file.error_message }}
          </span>
        </span>
        <div v-if="hasProcessingProgress(file)" class="source-processing-progress" aria-hidden="true">
          <div
            class="source-processing-fill"
            :style="{ width: getProcessingProgressPercent(file) + '%' }"
          ></div>
        </div>
      </div>

      <div v-if="manageMode" class="source-right">
        <div
          class="source-checkbox manage-checkbox"
          :class="{ checked: managedIds.has(file.id) }"
          role="checkbox"
          :aria-checked="managedIds.has(file.id)"
          :aria-label="file.file_name"
          @click.stop="toggleManaged(file.id)"
        >
          <svg v-if="managedIds.has(file.id)" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
        </div>
      </div>

      <div v-else-if="isActive(file)" class="source-right">
        <button
          type="button"
          class="source-stop-btn"
          :title="$t('ui.stopProcessing')"
          :aria-label="$t('ui.stopProcessing')"
          @click.stop="emit('cancel-files', [file.id])"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4 14H8V8h8v8z"/></svg>
        </button>
      </div>

      <div v-else-if="isRestartable(file)" class="source-right">
        <button
          type="button"
          class="source-stop-btn source-restart-btn"
          :title="$t('ui.restartProcessing')"
          :aria-label="$t('ui.restartProcessing')"
          @click.stop="emit('reprocess-files', [file.id])"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
        </button>
      </div>

      <div v-else-if="file.status === 'ready'" class="source-right">
        <div
          class="source-checkbox"
          :class="{ checked: selectedFileIds.includes(file.id) }"
          @click.stop="emit('toggle-file-selection', file.id)"
        >
          <svg v-if="selectedFileIds.includes(file.id)" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
          </svg>
        </div>
      </div>
    </div>
    <div v-if="contentHitFor(file)" class="source-hit-list">
      <button
        v-for="(snip, sn) in contentHitFor(file)!.snippets.slice(0, 2)"
        :key="sn"
        type="button"
        class="source-hit"
        :title="$t('ui.openSource')"
        @click="emit('open-file-preview', file.id)"
      >
        <span v-if="snip.page" class="source-hit-page">{{ $t('ui.refPage', { page: snip.page }) }}</span>
        <span class="source-hit-text" dir="auto"><template v-for="(seg, si) in snippetParts(snip)" :key="si"><mark v-if="seg.hit" class="search-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></span>
      </button>
      <span v-if="contentHitFor(file)!.count > 2" class="source-hit-more">{{ $t('ui.moreMatches', { count: contentHitFor(file)!.count - 2 }) }}</span>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { FileInfo } from '@/types'
import { t } from '@/i18n'
import {
  getStatusText,
  isAudioFile,
  isBibliographicName,
  isImageFile,
} from '@/views/projectPage/fileHelpers'
import { searchProject, type SearchHit, type SearchSnippet } from '@/services/api'
import { highlight, matchesAll, queryWords, snippetSegments, type TextSegment } from '@/utils/searchText'
import type { UploadingFile } from './types'

const props = defineProps<{
  files: FileInfo[]
  sortedFiles: FileInfo[]
  readyFiles: FileInfo[]
  selectedFileIds: string[]
  uploadingFiles: UploadingFile[]
  hoveringFileId: string | null
  openMenuFileId: string | null
  isAllSelected: boolean
  namingFileIds: string[]
}>()

const emit = defineEmits<{
  (e: 'toggle-collapse'): void
  (e: 'trigger-file-upload'): void
  (e: 'toggle-select-all'): void
  (e: 'open-file-preview', fileId: string): void
  (e: 'set-hovering-file', fileId: string | null): void
  (e: 'toggle-file-menu', fileId: string): void
  (e: 'rename-file', fileId: string, fileName: string): void
  (e: 'delete-file', fileId: string): void
  (e: 'toggle-file-selection', fileId: string): void
  (e: 'cancel-files', fileIds: string[]): void
  (e: 'delete-files', fileIds: string[]): void
  (e: 'reprocess-files', fileIds: string[]): void
  (e: 'suggest-names', fileIds: string[]): void
  (e: 'dismiss-naming', fileIds: string[]): void
  (e: 'set-file-selection', fileIds: string[], mode: 'add' | 'only'): void
}>()

// ── Search and filters ──────────────────────────────────────────────────────
type SourceFilter = 'all' | 'pdf' | 'web' | 'issues' | 'unnamed'
const route = useRoute()
const searchQuery = ref('')
const searchContent = ref(false)
const sourceFilter = ref<SourceFilter>('all')
const contentHits = ref<Map<string, SearchHit>>(new Map())
const contentSearching = ref(false)
const contentError = ref('')
let contentTimer: ReturnType<typeof setTimeout> | null = null
let contentSeq = 0

const filterOptions = computed<{ value: SourceFilter; label: string }[]>(() => [
  { value: 'pdf', label: 'PDF' },
  { value: 'web', label: t('ui.filterWebSources') },
  { value: 'issues', label: t('ui.filterSourceIssues') },
  { value: 'unnamed', label: t('ui.filterUnnamedSources') },
])

const words = computed(() => queryWords(searchQuery.value))
const isFiltering = computed(() => words.value.length > 0 || sourceFilter.value !== 'all')

function passesFilter(file: FileInfo): boolean {
  switch (sourceFilter.value) {
    case 'pdf': return file.file_type === 'pdf'
    case 'web': return !!file.source_url
    case 'issues': return file.status !== 'ready'
    case 'unnamed': return file.status === 'ready' && !isBibliographicName(file.file_name.replace(/\.[^.]+$/, ''))
    default: return true
  }
}

const visibleFiles = computed(() => props.sortedFiles.filter(file => {
  if (!passesFilter(file)) return false
  if (!words.value.length) return true
  return matchesAll(file.file_name, words.value) || (searchContent.value && contentHits.value.has(file.id))
}))
const visibleReadyIds = computed(() => visibleFiles.value.filter(f => f.status === 'ready').map(f => f.id))

function nameSegments(file: FileInfo): TextSegment[] {
  return highlight(file.file_name, words.value)
}

function contentHitFor(file: FileInfo): SearchHit | null {
  if (!searchContent.value || !words.value.length) return null
  const hit = contentHits.value.get(file.id)
  return hit && hit.snippets.length ? hit : null
}

function snippetParts(snip: SearchSnippet): TextSegment[] {
  return snippetSegments(snip.text, snip.ranges)
}

function clearSearch() {
  searchQuery.value = ''
  sourceFilter.value = 'all'
}

async function runContentSearch() {
  const query = searchQuery.value.trim()
  const projectId = String(route.params.id || '')
  const seq = ++contentSeq
  if (!searchContent.value || query.length < 2 || !projectId) {
    contentHits.value = new Map()
    contentSearching.value = false
    return
  }
  contentSearching.value = true
  contentError.value = ''
  try {
    const data = await searchProject(projectId, query, 'files')
    if (seq !== contentSeq) return
    contentHits.value = new Map((data.files || []).filter(h => h.count > 0).map(h => [h.id, h]))
  } catch (error: any) {
    if (seq === contentSeq) contentError.value = error?.response?.data?.detail || t('ui.searchFailed')
  } finally {
    if (seq === contentSeq) contentSearching.value = false
  }
}

watch([searchQuery, searchContent], () => {
  if (contentTimer) clearTimeout(contentTimer)
  contentTimer = setTimeout(runContentSearch, 350)
})

onBeforeUnmount(() => {
  if (contentTimer) clearTimeout(contentTimer)
})

// "Manage" mode: a separate selection (any status) for stopping or deleting several sources.
// It is independent of the chat source checkboxes.
const manageMode = ref(false)
const managedIds = ref<Set<string>>(new Set())

function isActive(file: FileInfo): boolean {
  return file.status === 'pending' || file.status === 'processing'
}

const activeFileIds = computed(() => props.files.filter(isActive).map(f => f.id))
const managedActiveIds = computed(() => props.files.filter(f => managedIds.value.has(f.id) && isActive(f)).map(f => f.id))
function isRestartable(file: FileInfo): boolean {
  return file.status === 'cancelled' || file.status === 'failed'
}

const restartableFileIds = computed(() => props.files.filter(isRestartable).map(f => f.id))
const managedRestartableIds = computed(() => props.files.filter(f => managedIds.value.has(f.id) && isRestartable(f)).map(f => f.id))
const managedReadyIds = computed(() => props.files.filter(f => managedIds.value.has(f.id) && f.status === 'ready').map(f => f.id))
const allManaged = computed(() => props.files.length > 0 && managedIds.value.size === props.files.length)
const someManaged = computed(() => managedIds.value.size > 0 && !allManaged.value)

function toggleManageMode() {
  if (manageMode.value) exitManageMode()
  else manageMode.value = true
}

function exitManageMode() {
  manageMode.value = false
  managedIds.value = new Set()
}

function toggleManaged(fileId: string) {
  const next = new Set(managedIds.value)
  if (next.has(fileId)) next.delete(fileId)
  else next.add(fileId)
  managedIds.value = next
}

function toggleManageAll() {
  managedIds.value = allManaged.value ? new Set() : new Set(props.files.map(f => f.id))
}

function onRowClick(file: FileInfo) {
  if (manageMode.value) toggleManaged(file.id)
  else if (file.status === 'ready') emit('open-file-preview', file.id)
}

// Forget deleted files; leave manage mode when nothing is left.
watch(() => props.files.map(f => f.id), (ids) => {
  const present = new Set(ids)
  const kept = [...managedIds.value].filter(id => present.has(id))
  if (kept.length !== managedIds.value.size) managedIds.value = new Set(kept)
  if (ids.length === 0) exitManageMode()
})

function getProcessingNumbers(file: FileInfo): { current: number; total: number } | null {
  const total = Number(file.processing_total || 0)
  if (!Number.isFinite(total) || total <= 0) return null
  const rawCurrent = Number(file.processing_current || 0)
  const current = Math.max(0, Math.min(total, Number.isFinite(rawCurrent) ? rawCurrent : 0))
  return { current, total }
}

function hasProcessingProgress(file: FileInfo): boolean {
  return file.status === 'processing' && getProcessingNumbers(file) !== null
}

function getProcessingProgressPercent(file: FileInfo): number {
  const progress = getProcessingNumbers(file)
  if (!progress) return 0
  return Math.round((progress.current / progress.total) * 100)
}

function getSourceStatusText(file: FileInfo): string {
  if (file.status === 'processing') {
    const progress = getProcessingNumbers(file)
    if (progress) return t('ui.processingProgress', progress)
    return file.processing_message || t('ui.readyToProcess')
  }
  return getStatusText(file.status)
}
</script>

<style scoped>
/* The box draws the frame and focus ring; the field inside stays plain. */
.source-search-input,
.source-search-input:focus,
.source-search-input:focus-visible {
  border: none;
  border-radius: 0;
  box-shadow: none;
  outline: none;
  padding: 0;
}

.source-search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: var(--focus-ring);
}

.source-search {
  padding: 0 12px 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.source-search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-white);
  color: var(--text-tertiary);
}

.source-search-box:focus-within,
.source-search-box.active {
  border-color: var(--primary-color);
}

.source-search-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-primary);
}

.source-search-input::-webkit-search-cancel-button {
  display: none;
}

.source-search-clear {
  display: flex;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 2px;
}

.source-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.source-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  background: var(--bg-white);
  color: var(--text-secondary);
  font-size: 11.5px;
  cursor: pointer;
}

.source-filter-chip.active {
  border-color: var(--primary-color);
  background: var(--primary-light);
  color: var(--primary-color);
}

.source-filter-sep {
  width: 1px;
  height: 14px;
  background: var(--border-color);
  margin: 0 2px;
}

.source-search-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.source-search-count {
  margin-right: auto;
}

.source-search-action {
  padding: 2px 8px;
  border: none;
  border-radius: 6px;
  background: var(--primary-light);
  color: var(--primary-color);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
}

.source-search-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--primary-light);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: source-search-spin 0.8s linear infinite;
}

@keyframes source-search-spin {
  to { transform: rotate(360deg); }
}

.source-search-error {
  margin: 0;
  font-size: 12px;
  color: #b42318;
}

.source-search-empty {
  padding: 16px 12px;
  font-size: 13px;
  color: var(--text-tertiary);
  text-align: center;
}

.search-hit {
  background: #fde68a;
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}

.source-hit-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: -2px 12px 6px 48px;
}

.source-hit {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: 4px 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-secondary);
  cursor: pointer;
}

.source-hit:hover {
  background: var(--bg-hover);
}

.source-hit-page {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-tertiary);
}

.source-hit-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.source-hit-more {
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 0 6px;
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

.panel-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

.panel-toggle-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: 50%;
  color: var(--text-tertiary);
}

.panel-header-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.panel-toggle-btn.active {
  background: var(--primary-soft);
  color: var(--primary-color);
}

.panel-toggle-btn:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.add-source-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 16px 16px 8px;
  height: 40px;
  padding: 0 20px;
  background: var(--bg-white);
  box-shadow: inset 0 0 0 1px var(--border-strong);
  border-radius: var(--radius-full);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  flex-shrink: 0;
}

.add-source-btn:hover {
  background: var(--bg-hover);
}

.upload-progress-container {
  padding: 8px 12px;
  margin-top: 8px;
  background: var(--bg-main);
  border-radius: 8px;
}

.upload-progress-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: var(--bg-white);
  border-radius: 8px;
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
}

.upload-progress-item:last-child {
  margin-bottom: 0;
}

.upload-progress-item.success {
  background: rgba(82, 196, 26, 0.08);
  border-color: rgba(82, 196, 26, 0.3);
}

.upload-progress-item.error {
  background: rgba(255, 77, 79, 0.08);
  border-color: rgba(255, 77, 79, 0.3);
}

.upload-file-name {
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-progress-bar {
  height: 6px;
  background: var(--border-color);
  border-radius: 3px;
  overflow: hidden;
}

.upload-progress-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 3px;
  transition: width 0.2s ease;
}

.upload-progress-item.success .upload-progress-fill {
  background: #52c41a;
}

.upload-progress-item.error .upload-progress-fill {
  background: var(--error-color);
}

.upload-status {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: right;
}

.upload-progress-item.success .upload-status {
  color: #52c41a;
}

.upload-progress-item.error .upload-status {
  color: var(--error-color);
}

.select-all-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 28px 8px 16px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.select-all-row:hover {
  background: var(--bg-hover);
}

.select-all-check {
  position: relative;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 2px solid var(--text-tertiary);
  border-radius: 3px;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.select-all-check::before {
  content: '';
  position: absolute;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  transition: background 0.15s;
}

.select-all-row:hover .select-all-check::before {
  background: rgba(0, 0, 0, 0.04);
}

.select-all-row:hover .select-all-check {
  border-color: var(--text-tertiary);
}

.select-all-check.checked {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: white;
}

.select-all-row:hover .select-all-check.checked::before {
  background: rgba(0, 0, 0, 0.06);
}

.sources-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.empty-sources {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-sources .empty-icon {
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.empty-sources p {
  font-size: 14px;
  margin-bottom: 10px;
}

.empty-sources .hint {
  font-size: 13px;
  color: var(--text-tertiary);
}

.source-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.3s;
  position: relative;
}

.source-item:hover {
  background: var(--bg-hover);
}

.source-item.ready:hover {
  background: var(--bg-hover);
}

.source-item.pending {
  cursor: default;
  background: rgba(0, 0, 0, 0.03);
}

.source-item.pending:hover {
  background: rgba(0, 0, 0, 0.05);
}

.source-item.processing {
  cursor: default;
  background: linear-gradient(
    90deg,
    rgba(74, 155, 168, 0.05) 0%,
    rgba(74, 155, 168, 0.12) 50%,
    rgba(74, 155, 168, 0.05) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 2s ease-in-out infinite;
}

.source-item.processing:hover {
  background: linear-gradient(
    90deg,
    rgba(74, 155, 168, 0.08) 0%,
    rgba(74, 155, 168, 0.15) 50%,
    rgba(74, 155, 168, 0.08) 100%
  );
  background-size: 200% 100%;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.source-left {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.source-icon {
  color: var(--primary-color);
  flex-shrink: 0;
}

.source-icon.image-icon {
  color: #34a853;
}

.source-icon.audio-icon {
  color: #9333ea;
}

.source-menu-wrapper {
  position: relative;
}

.source-menu-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: 4px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.source-menu-btn:hover {
  background: var(--bg-active);
  color: var(--text-primary);
}

.source-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  min-width: 120px;
  background: var(--bg-white);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
  overflow: hidden;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.dropdown-item:hover:not(.disabled) {
  background: var(--bg-hover);
}

.dropdown-item.disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
}

.source-info {
  flex: 1;
  min-width: 0;
}

.source-name {
  display: block;
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-status {
  font-size: 12px;
  color: var(--text-tertiary);
}

.source-status.ready {
  color: var(--success-color);
}

.source-status.processing {
  color: var(--primary-color);
}

.source-processing-progress {
  width: 100%;
  height: 4px;
  margin-top: 5px;
  background: rgba(74, 155, 168, 0.14);
  border-radius: 999px;
  overflow: hidden;
}

.source-processing-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: inherit;
  transition: width 0.25s ease;
}

.source-status.error,
.source-status.failed {
  color: var(--error-color);
}

.source-status.cancelled {
  color: var(--warning-color, #b45309);
}

.source-item.managing {
  cursor: pointer;
}

.source-item.managed {
  background: var(--primary-soft);
}

.source-item.managed:hover {
  background: var(--primary-soft);
}

.source-stop-btn {
  width: 32px;
  height: 32px;
  margin: -6px -7px -6px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.source-stop-btn:hover {
  background: var(--error-soft, rgba(239, 68, 68, 0.1));
  color: var(--error-color);
}

.source-stop-btn:focus-visible,
.manage-action:focus-visible,
.processing-stop-all:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.manage-bar {
  margin: 4px 12px 6px;
  padding: 4px 0 8px;
  border-radius: var(--radius-md);
  background: var(--bg-secondary, var(--bg-hover));
}

.manage-select-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px 6px 12px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  user-select: none;
}

.manage-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 2px 8px 0;
}

.manage-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-full);
  background: var(--bg-white);
  color: var(--text-primary);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.manage-action:hover:not(:disabled) {
  background: var(--bg-hover);
}

.manage-action:disabled {
  opacity: 0.45;
  cursor: default;
}

.manage-action.danger:not(:disabled) {
  color: var(--error-color);
  border-color: color-mix(in srgb, var(--error-color) 45%, transparent);
}

.manage-action.danger:hover:not(:disabled) {
  background: var(--error-soft, rgba(239, 68, 68, 0.08));
}

.manage-action.done {
  margin-left: auto;
  border-color: transparent;
  background: var(--primary-color);
  color: #fff;
}

.manage-action.done:hover {
  background: var(--primary-hover, var(--primary-color));
}

.select-all-check.partial {
  border-color: var(--primary-color);
}

.partial-mark {
  width: 8px;
  height: 2px;
  border-radius: 1px;
  background: var(--primary-color);
}

.naming-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 12px 2px;
  padding: 6px 4px 6px 10px;
  border-radius: var(--radius-md);
  background: var(--warning-soft, #fef7e0);
  font-size: 12.5px;
  color: var(--text-secondary);
}

.naming-banner-icon {
  flex: none;
  color: var(--warning-color, #b06000);
}

.naming-banner-text {
  flex: 1;
  min-width: 0;
  line-height: 1.4;
}

.naming-banner-action {
  flex: none;
  height: 28px;
  padding: 0 10px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--bg-white);
  color: var(--primary-color);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px var(--border-color);
}

.naming-banner-action:hover {
  background: var(--primary-soft);
}

.naming-banner-close {
  flex: none;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
}

.naming-banner-close:hover {
  background: rgba(0, 0, 0, 0.06);
}

.naming-banner-action:focus-visible,
.naming-banner-close:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.processing-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 4px 12px 2px;
  padding: 6px 6px 6px 12px;
  border-radius: var(--radius-md);
  background: var(--info-soft, var(--primary-soft));
  font-size: 12.5px;
  color: var(--text-secondary);
}

.processing-summary > span {
  min-width: 0;
  line-height: 1.35;
}

.processing-stop-all {
  flex: none;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--error-color);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
}

.stopped-summary {
  background: var(--warning-soft, #fef7e0);
}

.processing-stop-all.restart-all,
.source-restart-btn:hover {
  color: var(--primary-color);
}

.source-restart-btn:hover {
  background: var(--primary-soft);
}

.processing-stop-all.restart-all:hover {
  background: var(--primary-soft);
}

.processing-stop-all:hover {
  background: var(--error-soft, rgba(239, 68, 68, 0.1));
}

.source-status-reason {
  margin-left: 6px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.source-right {
  flex-shrink: 0;
  margin-left: auto;
  cursor: pointer;
}

.source-checkbox {
  position: relative;
  width: 18px;
  height: 18px;
  border: 2px solid var(--text-tertiary);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  background: transparent;
  cursor: pointer;
}

.source-checkbox::before {
  content: '';
  position: absolute;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: transparent;
  transition: background 0.15s;
}

.source-checkbox:hover::before {
  background: rgba(0, 0, 0, 0.04);
}

.source-checkbox:hover {
  border-color: var(--text-tertiary);
}

.source-checkbox.checked {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: white;
}

.source-checkbox.checked:hover::before {
  background: rgba(0, 0, 0, 0.06);
}
</style>
