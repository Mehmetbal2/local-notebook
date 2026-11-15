/** Quick tools are grouped into two tabs: learning aids and analysis outputs. */
export type ToolCategory = 'learn' | 'analyze'

export const TOOL_TYPES: Array<{
  type: string
  category?: ToolCategory
  titleKey: string
  tooltipKey: string
  descriptionKey?: string
  hintKey?: string
  builtinPromptKey?: string
  promptPlaceholderKey?: string
  color: string
  icon: string
  enabled: boolean
}> = [
  {
    type: 'study_guide',
    category: 'learn',
    titleKey: 'ui.studyGuide',
    tooltipKey: 'ui.studyGuideTooltip',
    descriptionKey: 'ui.studyGuideDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.studyGuideBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'blue',
    icon: 'study_guide',
    enabled: true
  },
  {
    type: 'flashcards',
    category: 'learn',
    titleKey: 'ui.flashcards',
    tooltipKey: 'ui.flashcardsTooltip',
    descriptionKey: 'ui.flashcardsDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.flashcardsBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'rose',
    icon: 'flashcards',
    enabled: true
  },
  {
    type: 'quiz',
    category: 'learn',
    titleKey: 'ui.quiz',
    tooltipKey: 'ui.quizTooltip',
    descriptionKey: 'ui.quizDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.quizBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'green',
    icon: 'quiz',
    enabled: true
  },
  {
    type: 'faq',
    category: 'learn',
    titleKey: 'ui.faq',
    tooltipKey: 'ui.faqTooltip',
    descriptionKey: 'ui.faqDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.faqBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'amber',
    icon: 'faq',
    enabled: true
  },
  {
    type: 'mind_map',
    category: 'learn',
    titleKey: 'ui.mindMap',
    tooltipKey: 'ui.mindMapTooltip',
    descriptionKey: 'ui.mindMapDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.mindMapBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'purple',
    icon: 'mind_map',
    enabled: true
  },
  {
    type: 'timeline',
    category: 'learn',
    titleKey: 'ui.timeline',
    tooltipKey: 'ui.timelineTooltip',
    descriptionKey: 'ui.timelineDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.timelineBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'teal',
    icon: 'timeline',
    enabled: true
  },
  {
    type: 'content_summary',
    category: 'analyze',
    titleKey: 'ui.contentSummary',
    tooltipKey: 'ui.contentSummaryTooltip',
    descriptionKey: 'ui.contentSummaryDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.contentSummaryBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'green',
    icon: 'summary',
    enabled: true
  },
  {
    type: 'briefing_doc',
    category: 'analyze',
    titleKey: 'ui.briefingDoc',
    tooltipKey: 'ui.briefingDocTooltip',
    descriptionKey: 'ui.briefingDocDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.briefingDocBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'blue',
    icon: 'briefing',
    enabled: true
  },
  {
    type: 'podcast',
    category: 'analyze',
    titleKey: 'ui.podcast',
    tooltipKey: 'ui.podcastTooltip',
    descriptionKey: 'ui.podcastDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.podcastBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'rose',
    icon: 'podcast',
    enabled: true
  },
  {
    type: 'audio_overview',
    category: 'analyze',
    titleKey: 'ui.audioOverview',
    tooltipKey: 'ui.audioOverviewTooltip',
    descriptionKey: 'ui.audioOverviewDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.audioOverviewBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'orange',
    icon: 'audio_overview',
    enabled: true
  },
  {
    type: 'objective_positioning',
    category: 'analyze',
    titleKey: 'ui.objectivePositioning',
    tooltipKey: 'ui.objectivePositioningTooltip',
    descriptionKey: 'ui.objectivePositioningDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.objectivePositioningBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'cyan',
    icon: 'positioning',
    enabled: true
  },
  {
    type: 'audience_profile',
    category: 'analyze',
    titleKey: 'ui.audienceProfile',
    tooltipKey: 'ui.audienceProfileTooltip',
    descriptionKey: 'ui.audienceProfileDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.audienceProfileBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'amber',
    icon: 'audience',
    enabled: true
  },
  {
    type: 'comparative_analysis',
    category: 'analyze',
    titleKey: 'ui.comparativeAnalysis',
    tooltipKey: 'ui.comparativeAnalysisTooltip',
    descriptionKey: 'ui.comparativeAnalysisDescription',
    hintKey: 'ui.quickToolConfigHint',
    builtinPromptKey: 'ui.comparativeAnalysisBuiltinPrompt',
    promptPlaceholderKey: 'ui.quickToolAdditionalRequirementsPlaceholder',
    color: 'indigo',
    icon: 'market',
    enabled: true
  },
  {
    type: 'custom_feature',
    category: 'analyze',
    titleKey: 'ui.customQuickTool',
    tooltipKey: 'ui.customQuickToolTooltip',
    descriptionKey: 'ui.customQuickToolDescription',
    hintKey: 'ui.customQuickToolPromptHint',
    promptPlaceholderKey: 'ui.customQuickToolPromptPlaceholder',
    color: 'custom',
    icon: 'custom',
    enabled: true
  },
  { type: 'deep_research', titleKey: 'ui.deepResearch', tooltipKey: 'ui.deepResearchTooltip', color: 'teal', icon: 'deep_research', enabled: false },
  { type: 'title_suggestion', titleKey: 'ui.titleSuggestion', tooltipKey: 'ui.titleSuggestionTooltip', color: 'purple', icon: 'title', enabled: false },
  { type: 'communication_copy', titleKey: 'ui.communicationCopy', tooltipKey: 'ui.communicationCopyTooltip', color: 'rose', icon: 'copy', enabled: false },
  { type: 'text_to_image', titleKey: 'ui.textToImage', tooltipKey: 'ui.textToImageTooltip', color: 'brown', icon: 'image', enabled: false },
  { type: 'reference_to_image', titleKey: 'ui.imageToImage', tooltipKey: 'ui.imageToImageTooltip', color: 'teal', icon: 'image_ref', enabled: false },
  { type: 'text_to_video', titleKey: 'ui.textToVideo', tooltipKey: 'ui.textToVideoTooltip', color: 'indigo', icon: 'video', enabled: false },
  { type: 'image_to_video', titleKey: 'ui.imageToVideo', tooltipKey: 'ui.imageToVideoTooltip', color: 'rose', icon: 'video_image', enabled: false },
  { type: 'start_end_to_video', titleKey: 'ui.startEndFrameVideo', tooltipKey: 'ui.startEndFrameVideoTooltip', color: 'amber', icon: 'video_frames', enabled: false },
]

export interface ToolIconDefinition {
  stroke?: boolean
  paths: readonly string[]
}

export const TOOL_ICON_SVGS: Record<string, ToolIconDefinition> = {
  podcast: {
    paths: ['M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z'],
  },
  study_guide: {
    paths: ['M5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82zM12 3 1 9l11 6 9-4.91V17h2V9L12 3z'],
  },
  briefing: {
    paths: ['M19 3h-4.18C14.4 1.84 13.3 1 12 1s-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z'],
  },
  faq: {
    paths: ['M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-1H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1z'],
  },
  note: {
    paths: ['M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h10l6-6V5c0-1.1-.9-2-2-2zM7 8h10v2H7V8zm5 6H7v-2h5v2zm2 5.5V14h5.5L14 19.5z'],
  },
  positioning: {
    paths: ['M12 2 4 5v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V5l-8-3zm0 2.18 6 2.25V11c0 4.28-2.72 8.24-6 9.75C8.72 19.24 6 15.28 6 11V6.43l6-2.25zM9 11h6v2H9v-2zm0-3h6v2H9V8z'],
  },
  audience: {
    paths: ['M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z'],
  },
  market: {
    paths: ['M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z'],
  },
  summary: {
    paths: ['M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z'],
  },
  timeline: {
    paths: ['M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z'],
  },
  mind_map: {
    paths: ['M22 11V3h-7v3H9V3H2v8h7V8h2v10h4v3h7v-8h-7v3h-2V8h2v3h7zM7 9H4V5h3v4zm10 6h3v4h-3v-4zm0-10h3v4h-3V5z'],
  },
  flashcards: {
    paths: ['M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z'],
  },
  quiz: {
    paths: ['M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z'],
  },
  audio_overview: {
    paths: ['M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z'],
  },
  deep_research: {
    paths: ['M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zM7 9h5v1H7V9zm0 2h4v1H7v-1zm0-4h5v1H7V7z'],
  },
  custom: {
    stroke: true,
    paths: ['M4 21v-7', 'M4 10V3', 'M12 21v-9', 'M12 8V3', 'M20 21v-5', 'M20 12V3', 'M2 14h4', 'M10 8h4', 'M18 16h4'],
  },
}

export function getToolIconDefinition(icon?: string): ToolIconDefinition {
  return (icon && TOOL_ICON_SVGS[icon]) || TOOL_ICON_SVGS.positioning!
}

export function getToolIconSvgProps(icon?: string, size = 20) {
  const def = getToolIconDefinition(icon)
  if (def.stroke) {
    return {
      viewBox: '0 0 24 24',
      width: size,
      height: size,
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': 2,
      'stroke-linecap': 'round' as const,
      'stroke-linejoin': 'round' as const,
    }
  }
  return {
    viewBox: '0 0 24 24',
    width: size,
    height: size,
    fill: 'currentColor',
  }
}

export const IMAGE_GENERATION_TYPES = ['text_to_image', 'reference_to_image']
export const VIDEO_GENERATION_TYPES = ['text_to_video', 'image_to_video', 'start_end_to_video']
