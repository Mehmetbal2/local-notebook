<template>
  <div class="settings-page">

    <header class="settings-header">
      <div class="settings-header-left">
        <button class="btn-back" @click="router.push('/')">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z" />
          </svg>
          {{ $t('ui.back') }}
        </button>
        <h1 class="settings-title">{{ $t('ui.settings') }}</h1>
      </div>
      <AppHeaderActions current="settings" />
    </header>

    <div class="settings-layout">

      <nav class="settings-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="nav-icon" v-html="tab.icon" />
          {{ $t(tab.labelKey) }}
        </button>
      </nav>


      <main class="settings-content">
        <div v-if="loading" class="loading-state">{{ $t('ui.loading') }}</div>

        <template v-else>

          <section v-if="activeTab === 'overview'" class="settings-section overview-section">
            <div class="section-header">
              <h2>{{ $t('ui.configurationOverview') }}</h2>
              <p class="section-desc">{{ $t('ui.currentConfigurationStatusForEachService') }}</p>
            </div>

            <div class="overview-grid">
              <div class="overview-card" @click="activeTab = 'llm'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.llm') }}</span>
                  <span class="overview-badge" :class="overviewLlmReady ? 'configured' : 'unconfigured'">
                    {{ overviewLlmReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">
                  {{ saved.llm_model || $t('ui.modelNotSet') }}
                  · {{ apiFormatLabel(saved.llm_api_format) }}
                </p>
              </div>


              <div class="overview-card" @click="activeTab = 'llm'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.vlm') }}</span>
                  <span class="overview-badge" :class="overviewVlmReady ? 'configured' : 'unconfigured'">
                    {{ overviewVlmReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">
                  {{ saved.vlm_model || $t('ui.modelNotSet') }}
                </p>
              </div>


              <div class="overview-card" @click="activeTab = 'embedding'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.embedding') }}</span>
                  <span class="overview-badge" :class="overviewEmbeddingReady ? 'configured' : 'unconfigured'">
                    {{ overviewEmbeddingReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">
                  {{ saved.embedding_source === 'local' ? $t('ui.localService') : $t('ui.custom') }}
                  <template v-if="saved.embedding_source === 'local'">· BAAI/bge-m3 ({{ saved.embedding_local_url || 'http://127.0.0.1:8001' }})</template>
                  <template v-else>· {{ saved.embedding_model || $t('ui.modelNotSet') }}</template>
                </p>
              </div>


              <div class="overview-card" @click="activeTab = 'pdf'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.pdfParsing') }}</span>
                  <span class="overview-badge" :class="overviewPdfReady ? 'configured' : 'unconfigured'">
                    {{ overviewPdfReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">
                  {{ pdfEngineSummary }}<template v-if="saved.ocr_model"> · {{ saved.ocr_model }}</template>
                </p>
              </div>


              <div class="overview-card" @click="activeTab = 'funasr'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.funasrTranscription') }}</span>
                  <span class="overview-badge" :class="overviewFunasrReady ? 'configured' : 'unconfigured'">
                    {{ overviewFunasrReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">
                  {{ saved.funasr_model || $t('ui.modelNotSet') }}
                </p>
              </div>


              <div class="overview-card" @click="activeTab = 'funasr'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.ttsSpeechSynthesis') }}</span>
                  <span class="overview-badge" :class="overviewTtsReady ? 'configured' : 'unconfigured'">
                    {{ overviewTtsReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">
                  {{ saved.tts_model ? `${saved.tts_model} · ${saved.tts_voice || 'deniz'}` : $t('ui.modelNotSet') }}
                </p>
              </div>


              <div class="overview-card" @click="activeTab = 'websearch'">
                <div class="overview-card-header">
                  <span class="overview-card-title">{{ $t('ui.webSearch') }}</span>
                  <span class="overview-badge" :class="overviewWebSearchReady ? 'configured' : 'unconfigured'">
                    {{ overviewWebSearchReady ? $t('ui.configured') : $t('ui.notConfigured') }}
                  </span>
                </div>
                <p class="overview-card-detail">SearXNG · {{ saved.searxng_base_url || 'http://127.0.0.1:8888' }}</p>
              </div>
            </div>
          </section>


          <section v-if="activeTab === 'llm'" class="settings-section">

            <div class="section-header">
              <h2>{{ $t('ui.llmModel') }}</h2>
              <p class="section-desc">{{ $t('ui.largeLanguageModelForQA') }}</p>
            </div>

            <div class="form-group">
              <label>API Key</label>
              <div class="input-row">
                <input
                  :type="showLlmKey ? 'text' : 'password'"
                  v-model="draft.llm_api_key"
                  placeholder="sk-..."
                  class="input"
                />
                <button class="btn-icon" @click="showLlmKey = !showLlmKey" :title="$t('ui.showHide')">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path v-if="showLlmKey" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                    <path v-else d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="form-group">
              <div class="label-row">
                <label>Base URL</label>
                <BaseUrlHelpTooltip />
              </div>
              <input
                v-model="draft.llm_base_url"
                :placeholder="draft.llm_api_format === 'anthropic' ? 'https://api.anthropic.com' : 'https://api.openai.com/v1'"
                class="input"
              />
              <p class="field-hint">
                Endpoint: <code>{{ resolvedLlmEndpointPreview }}</code>
              </p>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.requestFormat') }}</label>
              <div class="radio-group">
                <label class="radio-item">
                  <input type="radio" v-model="draft.llm_api_format" value="openai" />
                  <span>OpenAI Chat Completions</span>
                </label>
                <label class="radio-item">
                  <input type="radio" v-model="draft.llm_api_format" value="anthropic" />
                  <span>Anthropic Messages</span>
                </label>
              </div>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.modelName') }}</label>
              <input v-model="draft.llm_model" :placeholder="$t('ui.exampleDeepseekChatKimiGpt4o')" class="input" />
            </div>

            <div class="form-actions">
              <button class="btn-test" @click="testLlm" :disabled="testing.llm">
                {{ testing.llm ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <span v-if="testResult.llm" class="test-result" :class="testResult.llm.ok ? 'ok' : 'fail'">
                {{ testResult.llm.msg }}
              </span>
              <button class="btn-save" @click="save('llm')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>


            <div class="form-group easy-task-group">
              <label class="switch-row">
                <span class="switch-text">
                  {{ $t('ui.configureEasyTaskModel') }}
                  <span class="switch-sub">{{ $t('ui.economyModeSummariesDuringParsingUseACheaper') }}</span>
                </span>
                <span class="switch" :class="{ on: easyTaskEnabled }">
                  <input
                    type="checkbox"
                    :checked="easyTaskEnabled"
                    @change="toggleEasyTask(($event.target as HTMLInputElement).checked)"
                  />
                  <span class="switch-knob"></span>
                </span>
              </label>
              <template v-if="easyTaskEnabled">
                <input
                  v-model="draft.easy_task_llm"
                  :placeholder="$t('ui.eGDeepseekV4Flash')"
                  class="input easy-task-input"
                />
                <p class="field-hint">
                  {{ $t('ui.mustUseTheSameProviderAsTheMain') }}
                </p>
              </template>
              <div v-if="easyTaskEnabled" class="form-actions easy-task-actions">
                <button class="btn-test" @click="testEasyTask" :disabled="testing.easytask || !draft.easy_task_llm">
                  {{ testing.easytask ? $t('ui.testing') : $t('ui.testConnection') }}
                </button>
                <span v-if="testResult.easytask" class="test-result" :class="testResult.easytask.ok ? 'ok' : 'fail'">
                  {{ testResult.easytask.msg }}
                </span>
                <button class="btn-save" @click="save('easytask')" :disabled="saving">
                  {{ saving ? $t('ui.saving') : $t('ui.save') }}
                </button>
              </div>
            </div>

            <hr class="section-divider" />


            <div class="section-header">
              <h2>{{ $t('ui.vlmModel') }}</h2>
              <p class="section-desc">{{ $t('ui.visionLanguageModelForPdfImageAnalysis') }}</p>
            </div>

            <div class="form-group">
              <label>API Key</label>
              <div class="input-row">
                <input
                  :type="showVlmKey ? 'text' : 'password'"
                  v-model="draft.vlm_api_key"
                  placeholder="sk-..."
                  class="input"
                />
                <button class="btn-icon" @click="showVlmKey = !showVlmKey" :title="$t('ui.showHide')">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path v-if="showVlmKey" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                    <path v-else d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="form-group">
              <label>Base URL <span class="optional">{{ $t('ui.optional') }}</span></label>
              <input v-model="draft.vlm_base_url" placeholder="https://api.openai.com/v1" class="input" />
            </div>

            <div class="form-group">
              <label>{{ $t('ui.modelName') }}</label>
              <input v-model="draft.vlm_model" placeholder="gpt-4o" class="input" />
            </div>

            <div class="form-actions">
              <button class="btn-test" @click="testVlm" :disabled="testing.vlm">
                {{ testing.vlm ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <span v-if="testResult.vlm" class="test-result" :class="testResult.vlm.ok ? 'ok' : 'fail'">
                {{ testResult.vlm.msg }}
              </span>
              <button class="btn-save" @click="save('vlm')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>
          </section>


          <section v-if="activeTab === 'embedding'" class="settings-section">
            <div class="section-header">
              <h2>{{ $t('ui.embedding') }}</h2>
              <p class="section-desc">{{ $t('ui.convertTextIntoVectorsForSemanticSearch') }}</p>
            </div>

            <div class="warning-banner">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" class="warning-icon">
                <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
              </svg>
              <div>
                <strong>{{ $t('ui.chooseTheEmbeddingServiceBeforeFirstUse') }}</strong>
                <p>{{ $t('ui.afterSwitchingEmbeddingServiceVectorsForParsedDocuments') }}</p>
              </div>
            </div>

            <div class="form-group">
              <div class="radio-group">
                <label class="radio-item">
                  <input type="radio" v-model="draft.embedding_source" value="local" @change="onEmbeddingSourceChange" />
                  <span>{{ $t('ui.localServiceSentenceTransformersGpuRequired') }}</span>
                </label>
                <label class="radio-item">
                  <input type="radio" v-model="draft.embedding_source" value="custom" @change="onEmbeddingSourceChange" />
                  <span>{{ $t('ui.customOpenaiCompatibleApi') }}</span>
                </label>
              </div>
            </div>


            <template v-if="draft.embedding_source === 'custom'">
              <div class="form-group">
                <label>API Key</label>
                <input
                  type="password"
                  v-model="draft.embedding_api_key"
                  placeholder="sk-..."
                  class="input"
                />
              </div>
              <div class="form-group">
                <label>Base URL</label>
                <input
                  v-model="draft.embedding_base_url"
                  placeholder="https://api.openai.com/v1"
                  class="input"
                />
                <p class="field-hint">
                  Endpoint: <code>{{ (draft.embedding_base_url || 'https://api.openai.com/v1').replace(/\/+$/, '').replace(/\/embeddings$/, '') + '/embeddings' }}</code>
                </p>
              </div>
              <div class="form-group">
                <label>{{ $t('ui.modelName') }}</label>
                <input
                  v-model="draft.embedding_model"
                  placeholder="text-embedding-3-small"
                  class="input"
                />
              </div>
            </template>


            <template v-if="draft.embedding_source === 'local'">
              <div class="form-group">
                <p class="field-hint" style="margin-top: 0; margin-bottom: 12px; color: var(--text-secondary); line-height: 1.5;">
                  {{ $t('ui.localBgeM3Description') }}
                </p>
                <label>{{ $t('ui.serviceUrl') }}</label>
                <input
                  v-model="draft.embedding_local_url"
                  :placeholder="$t('ui.exampleLocalEmbeddingUrl')"
                  class="input"
                />
                <p class="field-hint">
                  {{ $t('ui.localEmbeddingServiceUrlStartItWith') }}<code>cd services/embedding && python server.py</code>
                  {{ $t('ui.doNotUseLocalhostInDockerDeploymentsInside') }}
                  {{ $t('ui.macWindowsUseHostDockerInternalLinuxUseLanIp') }}
                </p>
              </div>
            </template>

            <div class="form-actions">
              <button class="btn-test" @click="testEmbedding" :disabled="testing.embedding">
                {{ testing.embedding ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <button class="btn-test" @click="reindexEmbeddingDocuments" :disabled="reindexingEmbedding">
                {{ reindexingEmbedding ? $t('ui.reindexing') : $t('ui.reindexDocuments') }}
              </button>
              <span v-if="testResult.embedding" class="test-result" :class="testResult.embedding.ok ? 'ok' : 'fail'">
                {{ testResult.embedding.msg }}
              </span>
              <button class="btn-save" @click="save('embedding')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>
          </section>


          <section v-if="activeTab === 'pdf'" class="settings-section">
            <div class="section-header">
              <h2>{{ $t('ui.pdfParsingSection') }}</h2>
            </div>

            <div class="warning-banner">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" class="warning-icon">
                <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
              </svg>
              <div>
                <strong>{{ $t('ui.configureAPdfParsingServiceBeforeUploadingPdf') }}</strong>
                <p>{{ $t('ui.pdfParsingBannerText') }}</p>
              </div>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.pdfEngine') }}</label>
              <div class="radio-group">
                <label class="radio-item radio-item--stacked">
                  <input type="radio" v-model="draft.pdf_engine" value="auto" />
                  <span>{{ $t('ui.pdfEngineAuto') }}<small class="radio-hint">{{ $t('ui.pdfEngineAutoHint') }}</small></span>
                </label>
                <label class="radio-item radio-item--stacked">
                  <input type="radio" v-model="draft.pdf_engine" value="local" />
                  <span>{{ $t('ui.pdfEngineLocal') }}<small class="radio-hint">{{ $t('ui.pdfEngineLocalHint') }}</small></span>
                </label>
                <label class="radio-item radio-item--stacked">
                  <input type="radio" v-model="draft.pdf_engine" value="ocr" />
                  <span>{{ $t('ui.pdfEngineOcr') }}<small class="radio-hint">{{ $t('ui.pdfEngineOcrHint') }}</small></span>
                </label>
              </div>
            </div>

            <h3 class="subsection-title">{{ $t('ui.ocrServiceOptional') }}</h3>

            <div class="form-group">
              <label>API Key</label>
              <div class="input-row">
                <input
                  :type="showOcrKey ? 'text' : 'password'"
                  v-model="draft.ocr_api_key"
                  placeholder="sk-..."
                  class="input"
                />
                <button class="btn-icon" @click="showOcrKey = !showOcrKey" :title="$t('ui.showHide')">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path v-if="showOcrKey" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                    <path v-else d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="form-group">
              <label>Base URL</label>
              <input
                v-model="draft.ocr_base_url"
                placeholder="https://api.openai.com/v1"
                class="input"
              />
              <p class="field-hint">
                Endpoint: <code>{{ resolvedOcrEndpointPreview }}</code>
              </p>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.modelName') }}</label>
              <input
                v-model="draft.ocr_model"
                placeholder="deepseek-ocr-2, dots-ocr"
                class="input"
              />
            </div>

            <div class="form-actions">
              <button class="btn-test" @click="testOcr" :disabled="testing.ocr">
                {{ testing.ocr ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <span v-if="testResult.ocr" class="test-result" :class="testResult.ocr.ok ? 'ok' : 'fail'">
                {{ testResult.ocr.msg }}
              </span>
              <button class="btn-save" @click="save('pdf')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>
          </section>


          <section v-if="activeTab === 'funasr'" class="settings-section">
            <div class="section-header">
              <h2>{{ $t('ui.funasrTranscription') }}</h2>
              <p class="section-desc">{{ $t('ui.automaticallyTranscribeAudioFilesWithSupportForLong') }}</p>
            </div>

            <div class="form-group">
              <label>API Key</label>
              <div class="input-row">
                <input
                  :type="showFunasrKey ? 'text' : 'password'"
                  v-model="draft.funasr_api_key"
                  placeholder="sk-..."
                  class="input"
                />
                <button class="btn-icon" @click="showFunasrKey = !showFunasrKey" :title="$t('ui.showHide')">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path v-if="showFunasrKey" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                    <path v-else d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="form-group">
              <label>Base URL</label>
              <input
                type="text"
                v-model="draft.funasr_base_url"
                placeholder="https://api.openai.com/v1"
                class="input"
              />
              <p class="field-hint">
                Endpoint: <code>{{ resolvedAsrEndpointPreview }}</code>
              </p>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.modelName') }}</label>
              <input
                v-model="draft.funasr_model"
                placeholder="qwen3-asr-1.7b, whisper-1"
                class="input"
              />
            </div>

            <div class="form-actions">
              <button class="btn-test" @click="testFunasr" :disabled="testing.funasr">
                {{ testing.funasr ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <span v-if="testResult.funasr" class="test-result" :class="testResult.funasr.ok ? 'ok' : 'fail'">
                {{ testResult.funasr.msg }}
              </span>
              <button class="btn-save" @click="save('funasr')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>

            <hr class="section-divider" />

            <div class="section-header">
              <h2>{{ $t('ui.ttsSpeechSynthesis') }}</h2>
              <p class="section-desc">{{ $t('ui.convertTextIntoNaturalSpeechWithCustomApi') }}</p>
            </div>

            <div class="form-group">
              <label>API Key</label>
              <div class="input-row">
                <input
                  :type="showTtsKey ? 'text' : 'password'"
                  v-model="draft.tts_api_key"
                  placeholder="sk-..."
                  class="input"
                />
                <button class="btn-icon" @click="showTtsKey = !showTtsKey" :title="$t('ui.showHide')">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path v-if="showTtsKey" d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>
                    <path v-else d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>
                  </svg>
                </button>
              </div>
            </div>

            <div class="form-group">
              <label>Base URL</label>
              <input
                type="text"
                v-model="draft.tts_base_url"
                placeholder="https://api.openai.com/v1"
                class="input"
              />
              <p class="field-hint">
                Endpoint: <code>{{ resolvedTtsEndpointPreview }}</code>
              </p>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.modelName') }}</label>
              <input
                v-model="draft.tts_model"
                placeholder="voxcpm2, tts-1"
                class="input"
              />
            </div>

            <div class="form-group">
              <label>{{ $t('ui.voiceName') }}</label>
              <input
                v-model="draft.tts_voice"
                placeholder="deniz, ece, emre, kaan"
                class="input"
              />
              <p class="field-hint">{{ $t('ui.voiceNameHint') }}</p>
            </div>

            <div class="form-actions">
              <button class="btn-test" @click="testTts" :disabled="testing.tts">
                {{ testing.tts ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <span v-if="testResult.tts" class="test-result" :class="testResult.tts.ok ? 'ok' : 'fail'">
                {{ testResult.tts.msg }}
              </span>
              <button class="btn-save" @click="save('tts')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>
          </section>


          <section v-if="activeTab === 'websearch'" class="settings-section">
            <div class="section-header">
              <h2>{{ $t('ui.webSearch') }}</h2>
              <p class="section-desc">{{ $t('ui.webSearchSectionDesc') }}</p>
            </div>

            <div class="form-group">
              <label>{{ $t('ui.searxngAddress') }}</label>
              <input v-model="draft.searxng_base_url" placeholder="http://127.0.0.1:8888" class="input" />
              <p class="field-hint">{{ $t('ui.searxngAddressHint') }}</p>
            </div>

            <div class="form-actions">
              <button class="btn-test" @click="testWebSearch" :disabled="testing.websearch">
                {{ testing.websearch ? $t('ui.testing') : $t('ui.testConnection') }}
              </button>
              <span v-if="testResult.websearch" class="test-result" :class="testResult.websearch.ok ? 'ok' : 'fail'">
                {{ testResult.websearch.msg }}
              </span>
              <button class="btn-save" @click="save('websearch')" :disabled="saving">
                {{ saving ? $t('ui.saving') : $t('ui.save') }}
              </button>
            </div>
          </section>

        </template>


        <transition name="toast">
          <div v-if="toast.show" class="toast" :class="toast.type">
            {{ toast.msg }}
          </div>
        </transition>


        <transition name="modal">
          <div v-if="confirmDialog.show" class="modal-overlay" @click.self="confirmDialog.show = false">
            <div class="modal-card">
              <div class="modal-header">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="#e65100">
                  <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
                </svg>
                <h3>{{ confirmDialog.title || $t('ui.confirmEmbeddingServiceSwitch') }}</h3>
              </div>
              <div class="modal-body">
                <p>{{ confirmDialog.msg }}</p>
                <p class="modal-warn">{{ confirmDialog.action === 'reindex' ? $t('ui.reindexModalWarn') : $t('ui.makeSureAllFilesAndResultsAreSaved') }}</p>
              </div>
              <div class="modal-actions">
                <button class="btn-cancel" @click="confirmDialog.show = false">{{ $t('ui.cancel') }}</button>
                <button class="btn-danger" @click="confirmForceSave">{{ confirmDialog.action === 'reindex' ? $t('ui.reindexDocuments') : $t('ui.confirmSwitch') }}</button>
              </div>
            </div>
          </div>
        </transition>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getSettings, updateSettings, checkPreflight, type SettingsMap } from '../services/api'
import { getToken } from '../services/auth'
import BaseUrlHelpTooltip from '../components/common/BaseUrlHelpTooltip.vue'
import AppHeaderActions from '../components/common/AppHeaderActions.vue'
import { t } from '../i18n'

const router = useRouter()
const route = useRoute()



const tabs = [
  {
    key: 'overview',
    labelKey: 'ui.overview',
    icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>',
  },
  {
    key: 'llm',
    labelKey: 'ui.modelSettings',
    icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 17.93V18a1 1 0 0 0-2 0v1.93A8 8 0 0 1 4.07 13H6a1 1 0 0 0 0-2H4.07A8 8 0 0 1 11 4.07V6a1 1 0 0 0 2 0V4.07A8 8 0 0 1 19.93 11H18a1 1 0 0 0 0 2h1.93A8 8 0 0 1 13 19.93z"/></svg>',
  },
  {
    key: 'embedding',
    labelKey: 'ui.embedding',
    icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M4 8h4V4H4v4zm6 12h4v-4h-4v4zm-6 0h4v-4H4v4zm0-6h4v-4H4v4zm6 0h4v-4h-4v4zm6-10v4h4V4h-4zm-6 4h4V4h-4v4zm6 6h4v-4h-4v4zm0 6h4v-4h-4v4z"/></svg>',
  },
  {
    key: 'pdf',
    labelKey: 'ui.pdfParsing',
    icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>',
  },
  {
    key: 'funasr',
    labelKey: 'ui.audio',
    icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 15c1.66 0 2.99-1.34 2.99-3L15 6c0-1.66-1.34-3-3-3S9 4.34 9 6v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 15 6.7 12H5c0 3.42 2.72 6.23 6 6.72V22h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>',
  },
  {
    key: 'websearch',
    labelKey: 'ui.webSearch',
    icon: '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
  },
]

const validTabs = tabs.map(t => t.key)
const initialTab = validTabs.includes(route.query.tab as string) ? (route.query.tab as string) : 'overview'
const activeTab = ref(initialTab)


watch(activeTab, (tab) => {
  router.replace({ query: { ...route.query, tab } })
})

watch(() => route.query.tab, (tab) => {
  if (tab && validTabs.includes(tab as string) && tab !== activeTab.value) {
    activeTab.value = tab as string
  }
})


const loading = ref(true)
const saving = ref(false)
const draft = reactive<SettingsMap>({})
const saved = reactive<SettingsMap>({})

const showLlmKey = ref(false)
const showVlmKey = ref(false)
const showOcrKey = ref(false)
const showFunasrKey = ref(false)
const showTtsKey = ref(false)

// The easy task toggle is derived from whether easy_task_llm has a value.
// Turning it off clears the easy model and saves immediately; the backend falls back to the main LLM.
const easyTaskEnabled = ref(false)
async function toggleEasyTask(on: boolean) {
  easyTaskEnabled.value = on
  if (on) return
  testResult.easytask = null
  const hadValue = !!(draft.easy_task_llm || saved.easy_task_llm)
  draft.easy_task_llm = ''
  if (hadValue) await save('easytask')
}

const DEFAULT_SETTINGS: SettingsMap = {
  llm_api_key: '',
  llm_base_url: '',
  llm_model: '',
  llm_api_format: 'openai',
  easy_task_llm: '',

  vlm_api_key: '',
  vlm_base_url: '',
  vlm_model: '',

  embedding_source: 'local',
  embedding_model: '',
  embedding_api_key: '',
  embedding_base_url: '',
  embedding_local_url: 'http://127.0.0.1:8001',

  ocr_base_url: '',
  ocr_api_key: '',
  ocr_model: '',
  pdf_engine: 'auto',

  funasr_base_url: '',
  funasr_api_key: '',
  funasr_model: '',

  tts_base_url: '',
  tts_api_key: '',
  tts_model: '',
  tts_voice: 'deniz',

  searxng_base_url: 'http://127.0.0.1:8888',
}

const resolvedLlmEndpointPreview = computed(() => {
  const format = draft.llm_api_format || 'openai'
  const raw = (draft.llm_base_url || (format === 'anthropic' ? 'https://api.anthropic.com' : 'https://api.openai.com/v1')).trim().replace(/\/+$/, '')
  if (format === 'anthropic') {
    const base = raw.replace(/\/(v1\/messages|messages|v1)$/, '')
    return `${base}/v1/messages`
  }
  const base = raw.replace(/\/(chat\/completions|completions)$/, '')
  return `${base}/chat/completions`
})
const resolvedOcrEndpointPreview = computed(() => {
  const raw = (draft.ocr_base_url || 'https://api.openai.com/v1').trim().replace(/\/+$/, '')
  return raw.endsWith('/ocr') ? raw : `${raw}/ocr`
})
const resolvedAsrEndpointPreview = computed(() => {
  const raw = (draft.funasr_base_url || 'https://api.openai.com/v1').trim().replace(/\/+$/, '')
  return raw.endsWith('/audio/transcriptions') ? raw : `${raw}/audio/transcriptions`
})
const resolvedTtsEndpointPreview = computed(() => {
  const raw = (draft.tts_base_url || 'https://api.openai.com/v1').trim().replace(/\/+$/, '')
  return raw.endsWith('/audio/speech') ? raw : `${raw}/audio/speech`
})


const preflightEmbeddingReady = ref(true)
const overviewLlmReady = computed(() => !!(saved.llm_api_key && saved.llm_base_url && saved.llm_model))
const overviewVlmReady = computed(() => !!(saved.vlm_api_key && saved.vlm_model))
const overviewEmbeddingReady = computed(() => {
  if (saved.embedding_source === 'custom') return !!(saved.embedding_base_url && saved.embedding_model)
  return preflightEmbeddingReady.value && Boolean((saved.embedding_local_url || '').trim())
})
const overviewWebSearchReady = computed(() => saved.web_search_verified === 'true')
const overviewOcrReady = computed(() => !!(saved.ocr_api_key && saved.ocr_base_url && saved.ocr_model))
// The local engine is always available; only the OCR-only mode depends on the service.
const overviewPdfReady = computed(() => saved.pdf_engine !== 'ocr' || overviewOcrReady.value)
const pdfEngineSummary = computed(() => {
  if (saved.pdf_engine === 'local') return t('ui.pdfEngineSummaryLocal')
  if (saved.pdf_engine === 'ocr') return t('ui.pdfEngineSummaryOcr')
  return t('ui.pdfEngineSummaryAuto')
})
const overviewFunasrReady = computed(() => !!(saved.funasr_api_key && saved.funasr_base_url && saved.funasr_model))
const overviewTtsReady = computed(() => !!(saved.tts_api_key && saved.tts_base_url && saved.tts_model))

const testing = reactive({ llm: false, easytask: false, vlm: false, embedding: false, ocr: false, funasr: false, tts: false, websearch: false })
const testResult = reactive<{
  llm: { ok: boolean; msg: string } | null
  easytask: { ok: boolean; msg: string } | null
  vlm: { ok: boolean; msg: string } | null
  embedding: { ok: boolean; msg: string } | null
  ocr: { ok: boolean; msg: string } | null
  funasr: { ok: boolean; msg: string } | null
  tts: { ok: boolean; msg: string } | null
  websearch: { ok: boolean; msg: string } | null
}>({ llm: null, easytask: null, vlm: null, embedding: null, ocr: null, funasr: null, tts: null, websearch: null })

const toast = reactive({ show: false, msg: '', type: 'success' as 'success' | 'error' })


const savedEmbeddingSource = ref('')
const reindexingEmbedding = ref(false)
const confirmDialog = reactive({ show: false, title: '', msg: '', action: 'switch' as 'switch' | 'reindex' })


onMounted(async () => {
  try {
    const [remote, preflight] = await Promise.all([
      getSettings(),
      checkPreflight().catch(() => null),
    ])
    if (preflight) {
      preflightEmbeddingReady.value = !!preflight.embedding_ready
    }
    if (remote.embedding_source && remote.embedding_source !== 'custom' && remote.embedding_source !== 'local') {
      remote.embedding_source = 'local'
    }
    if (!['auto', 'local', 'ocr'].includes(remote.pdf_engine || '')) {
      remote.pdf_engine = 'auto'
    }
    savedEmbeddingSource.value = remote.embedding_source || ''
    Object.assign(saved, DEFAULT_SETTINGS, remote)
    Object.assign(draft, DEFAULT_SETTINGS, remote)
    easyTaskEnabled.value = !!(remote.easy_task_llm && remote.easy_task_llm.trim())
  } finally {
    loading.value = false
  }
})


const SECTION_KEYS: Record<string, (keyof SettingsMap)[]> = {
  llm: ['llm_api_key', 'llm_base_url', 'llm_model', 'llm_api_format'],
  easytask: ['easy_task_llm'],
  vlm: ['vlm_api_key', 'vlm_base_url', 'vlm_model'],
  embedding: ['embedding_source', 'embedding_model', 'embedding_api_key', 'embedding_base_url', 'embedding_local_url'],
  pdf: ['pdf_engine', 'ocr_base_url', 'ocr_api_key', 'ocr_model'],
  funasr: ['funasr_base_url', 'funasr_api_key', 'funasr_model'],
  tts: ['tts_base_url', 'tts_api_key', 'tts_model', 'tts_voice'],
  websearch: ['searxng_base_url'],
}

async function save(section: string, force = false) {

  if (section === 'llm' && !draft.llm_base_url) {
    showToast(t('ui.customLlmRequiresABaseUrl'), 'error')
    return
  }

  if (section === 'embedding' && !force) {
    const oldSource = savedEmbeddingSource.value
    const newSource = draft.embedding_source
    const modelChanged = newSource === 'custom' && (draft.embedding_model || '').trim() !== (saved.embedding_model || '').trim() && Boolean(saved.embedding_model || oldSource)
    if ((oldSource && newSource && oldSource !== newSource) || modelChanged) {
      const fromLabel = modelChanged ? (saved.embedding_model || sourceLabel(oldSource)) : sourceLabel(oldSource)
      const toLabel = modelChanged ? (draft.embedding_model || sourceLabel(newSource || '')) : sourceLabel(newSource || '')
      confirmDialog.title = t('ui.confirmEmbeddingServiceSwitch')
      confirmDialog.msg = t('ui.embeddingSwitchConfirmationMessage', { from: fromLabel, to: toLabel })
      confirmDialog.action = 'switch'
      confirmDialog.show = true
      return
    }
  }

  saving.value = true
  try {
    const keys = SECTION_KEYS[section] ?? []
    const payload: Partial<SettingsMap> = {}
    for (const k of keys) {
      payload[k] = draft[k]
    }
    const updated = await updateSettings(payload, force)
    Object.assign(saved, DEFAULT_SETTINGS, updated)
    Object.assign(draft, updated)
    savedEmbeddingSource.value = saved.embedding_source || ''
    showToast(t('ui.savedSuccessfully'), 'success')
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    if (detail) {
      showToast(detail, 'error')
    } else {
      showToast(t('ui.saveFailedCheckNetwork'), 'error')
    }
  } finally {
    saving.value = false
  }
}

function sourceLabel(source: string): string {
  return { local: t('ui.localService'), custom: t('ui.custom') }[source] || source
}

function apiFormatLabel(format?: string): string {
  return format === 'anthropic' ? 'Anthropic Messages' : 'OpenAI Chat'
}

function confirmForceSave() {
  const action = confirmDialog.action
  confirmDialog.show = false
  if (action === 'reindex') {
    executeReindexEmbeddingDocuments()
  } else {
    save('embedding', true)
  }
}


function authHeader() {
  return { Authorization: `Bearer ${getToken() ?? ''}` }
}

async function testLlm() {
  testing.llm = true
  testResult.llm = null
  try {
    if (!draft.llm_base_url) {
      testResult.llm = { ok: false, msg: t('ui.enterABaseUrl') }
      return
    }
    const body = {
      source: 'custom',
      api_key: draft.llm_api_key,
      base_url: draft.llm_base_url,
      model: draft.llm_model,
      api_format: draft.llm_api_format || 'openai',
    }
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/llm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    testResult.llm = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.llm = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.llm = false
  }
}

async function testEasyTask() {
  // Easy-task testing reuses the main LLM provider credentials and only swaps the model name.
  testing.easytask = true
  testResult.easytask = null
  try {
    if (!draft.llm_base_url) {
      testResult.easytask = { ok: false, msg: t('ui.enterABaseUrl') }
      return
    }
    const body = {
      source: 'custom',
      api_key: draft.llm_api_key,
      base_url: draft.llm_base_url,
      model: draft.easy_task_llm,
      api_format: draft.llm_api_format || 'openai',
    }
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/easy-task-llm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    testResult.easytask = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.easytask = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.easytask = false
  }
}

async function testVlm() {
  testing.vlm = true
  testResult.vlm = null
  try {
    const body = {
      source: 'custom',
      api_key: draft.vlm_api_key,
      base_url: draft.vlm_base_url,
      model: draft.vlm_model,
    }
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/vlm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    testResult.vlm = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.vlm = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.vlm = false
  }
}

function onEmbeddingSourceChange() {
  testResult.embedding = null
  if (draft.embedding_source === 'local' && !(draft.embedding_local_url || '').trim()) {
    draft.embedding_local_url = 'http://127.0.0.1:8001'
  }
}

function reindexEmbeddingDocuments() {
  confirmDialog.title = t('ui.confirmReindexTitle')
  confirmDialog.msg = t('ui.confirmReindexMessage')
  confirmDialog.action = 'reindex'
  confirmDialog.show = true
}

async function executeReindexEmbeddingDocuments() {
  reindexingEmbedding.value = true
  try {
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/embedding/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ confirm: true }),
    })
    const data = await res.json()
    if (res.ok && data.ok) {
      showToast(data.msg || t('ui.savedSuccessfully'), 'success')
    } else {
      showToast(data.detail || data.msg || t('ui.saveFailedCheckNetwork'), 'error')
    }
  } catch {
    showToast(t('ui.saveFailedCheckNetwork'), 'error')
  } finally {
    reindexingEmbedding.value = false
  }
}

async function testEmbedding() {
  testing.embedding = true
  testResult.embedding = null
  try {

    const body: Record<string, string | undefined> = {
      source: draft.embedding_source || undefined,
    }
    if (draft.embedding_source === 'custom') {
      body.api_key = draft.embedding_api_key || undefined
      body.base_url = draft.embedding_base_url || undefined
      body.model = draft.embedding_model || undefined
    } else if (draft.embedding_source === 'local') {
      body.base_url = draft.embedding_local_url || 'http://127.0.0.1:8001'
      body.model = 'bge-m3'
    }
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/embedding`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    testResult.embedding = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.embedding = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.embedding = false
  }
}

async function testOcr() {
  testing.ocr = true
  testResult.ocr = null
  try {
    if (!draft.ocr_base_url) {
      testResult.ocr = { ok: false, msg: t('ui.enterABaseUrl') }
      return
    }
    const payload = {
      api_key: draft.ocr_api_key || '',
      base_url: draft.ocr_base_url || '',
      model: draft.ocr_model || '',
    }

    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/ocr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    testResult.ocr = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.ocr = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.ocr = false
  }
}

async function testFunasr() {
  testing.funasr = true
  testResult.funasr = null
  try {
    if (!draft.funasr_base_url) {
      testResult.funasr = { ok: false, msg: t('ui.enterABaseUrl') }
      return
    }
    const payload = {
      api_key: draft.funasr_api_key || '',
      base_url: draft.funasr_base_url || '',
      model: draft.funasr_model || '',
    }
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/funasr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    testResult.funasr = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.funasr = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.funasr = false
  }
}

async function testTts() {
  testing.tts = true
  testResult.tts = null
  try {
    if (!draft.tts_base_url) {
      testResult.tts = { ok: false, msg: t('ui.enterABaseUrl') }
      return
    }
    const payload = {
      api_key: draft.tts_api_key || '',
      base_url: draft.tts_base_url || '',
      model: draft.tts_model || '',
      voice: draft.tts_voice || 'deniz',
    }
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    testResult.tts = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.tts = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.tts = false
  }
}

async function testWebSearch() {
  testing.websearch = true
  testResult.websearch = null
  try {
    const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/api/settings/test/web-search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ base_url: draft.searxng_base_url || '' }),
    })
    const data = await res.json()
    testResult.websearch = { ok: !!data.ok, msg: data.msg || (data.ok ? t('ui.connected') : t('ui.connectionFailed')) }
  } catch {
    testResult.websearch = { ok: false, msg: t('ui.cannotConnect') }
  } finally {
    testing.websearch = false
  }
}


function showToast(msg: string, type: 'success' | 'error') {
  toast.msg = msg
  toast.type = type
  toast.show = true
  setTimeout(() => { toast.show = false }, type === 'error' ? 5000 : 2500)
}
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg-main);
}


.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 24px;
  height: 56px;
  background: var(--bg-main);
  flex-shrink: 0;
}

.settings-header-left,
.settings-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.settings-header-left {
  min-width: 0;
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-back:hover { background: var(--bg-hover); }

.btn-header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s;
}
.btn-header-icon:hover { background: var(--bg-hover); }

.settings-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.user-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 13px;
  color: var(--text-tertiary);
  cursor: default;
}

@media (max-width: 640px) {
  .settings-header {
    padding: 0 12px;
  }

  .settings-title {
    display: none;
  }

  .user-badge {
    padding: 6px 8px;
  }
}


.settings-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}


.settings-nav {
  width: 180px;
  flex-shrink: 0;
  padding: 8px 12px;
  width: 220px;
  background: var(--bg-main);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-item.active { background: var(--primary-soft); color: var(--on-primary-soft); font-weight: 500; }

.nav-icon { display: flex; align-items: center; flex-shrink: 0; }


.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: 32px 48px;
  position: relative;
}

.loading-state {
  color: var(--text-tertiary);
  font-size: 14px;
}


.settings-section {
  max-width: 560px;
}

.section-header {
  margin-bottom: 28px;
}
.section-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px;
}
.section-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.5;
}
.section-desc a {
  color: var(--primary-color);
  text-decoration: none;
}
.section-desc a:hover {
  text-decoration: underline;
}


.section-divider {
  border: none;
  border-top: 1px solid var(--border-color);
  margin: 32px 0;
}


.warning-banner {
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 20px;
  background: #fff8e1;
  border: 1px solid #ffe082;
  border-radius: 8px;
  font-size: 13px;
  color: #5d4037;
  line-height: 1.5;
}
.warning-banner strong {
  display: block;
  margin-bottom: 2px;
  color: #e65100;
  font-size: 13px;
}
.warning-banner p {
  margin: 0;
  font-size: 12px;
  color: #795548;
}
.warning-icon {
  flex-shrink: 0;
  color: #f57c00;
  margin-top: 1px;
}

.radio-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  vertical-align: middle;
}
.radio-tag.recommend {
  background: #e8f5e9;
  color: #2e7d32;
}


.form-group {
  margin-bottom: 20px;
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.label-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.label-row label {
  margin-bottom: 0;
}
.optional {
  font-weight: 400;
  color: var(--text-disabled);
}

.input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
  background: #fff;
  box-sizing: border-box;
  transition: border-color 0.15s;
  outline: none;
}
.input:focus { border-color: var(--text-primary); }
.input-sm { width: 100%; }

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.input-row .input { flex: 1; }

.btn-icon {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: background 0.15s;
}
.btn-icon:hover { background: var(--bg-hover); }

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.radio-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
}
.radio-item input { cursor: pointer; }
.radio-item a {
  color: var(--primary-color);
  text-decoration: none;
}
.radio-item a:hover {
  text-decoration: underline;
}

.field-hint {
  font-size: 12px;
  color: var(--text-disabled);
  margin: 4px 0 0;
}


.easy-task-group {
  margin-top: 8px;
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}
.switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 0;
  cursor: pointer;
}
.switch-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.switch-sub {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-disabled);
  line-height: 1.5;
}
.switch {
  position: relative;
  flex-shrink: 0;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: #d0d0cc;
  transition: background 0.15s;
}
.switch.on { background: var(--text-primary); }
.switch input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}
.switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.15s;
}
.switch.on .switch-knob { transform: translateX(18px); }
.easy-task-input { margin-top: 12px; }
.easy-task-actions { margin-top: 16px; padding-top: 16px; }


.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

.btn-save {
  margin-left: auto;
  padding: 8px 20px;
  background: var(--text-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-save:hover:not(:disabled) { opacity: 0.85; }
.btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-test {
  padding: 8px 16px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-full);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-test:hover:not(:disabled) { background: var(--bg-hover); }
.btn-test:disabled { opacity: 0.5; cursor: not-allowed; }

.test-result {
  font-size: 13px;
  margin-right: auto;
}
.test-result.ok { color: #2e7d32; }
.test-result.fail { color: var(--error-color); }


.toast {
  position: fixed;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  z-index: 9999;
  pointer-events: none;
}
.toast.success { background: var(--text-primary); color: #fff; }
.toast.error   { background: var(--error-color); color: #fff; }

.toast-enter-active, .toast-leave-active { transition: opacity 0.25s, transform 0.25s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }


.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.modal-card {
  background: #fff;
  border-radius: var(--radius-xl);
  width: 440px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 24px 0;
}
.modal-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.modal-body {
  padding: 16px 24px 20px;
}
.modal-body p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 10px;
}
.modal-warn {
  font-weight: 500;
  color: var(--error-color) !important;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 24px 20px;
}
.btn-cancel {
  padding: 8px 18px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-full);
  background: #fff;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.btn-cancel:hover { background: var(--bg-hover); }
.btn-danger {
  padding: 8px 18px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--error-color);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-danger:hover { opacity: 0.85; }

.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }


.overview-section {
  max-width: 680px;
}
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.overview-card {
  padding: 16px;
  background: #fff;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.overview-card:hover {
  border-color: #ccc;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.overview-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.overview-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.overview-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
}
.overview-badge.configured {
  background: #e8f5e9;
  color: #2e7d32;
}
.overview-badge.unconfigured {
  background: #fff3e0;
  color: #e65100;
}
.overview-card-detail {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.overview-card-detail.muted {
  color: #aaa;
}
.overview-card.disabled-card {
  opacity: 0.6;
  cursor: default;
}
.overview-card.disabled-card:hover {
  border-color: var(--border-color);
  box-shadow: none;
}
.overview-badge.coming-soon {
  background: var(--bg-hover);
  color: var(--text-disabled);
}


.coming-soon-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 24px;
  color: #ccc;
  text-align: center;
}
.coming-soon-placeholder p {
  font-size: 14px;
  color: var(--text-disabled);
  margin: 0;
}

.radio-item--stacked {
  align-items: flex-start;
}

.radio-item--stacked input {
  margin-top: 3px;
}

.radio-hint {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.subsection-title {
  margin: 28px 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
}
</style>
