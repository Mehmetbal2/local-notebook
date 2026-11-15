export const DOCUMENT_FILE_EXTENSIONS = [
  'pdf', 'docx', 'doc', 'txt', 'md', 'markdown', 'htm', 'html', 'epub',
] as const

export const IMAGE_FILE_EXTENSIONS = ['jpg', 'jpeg', 'png'] as const
export const AUDIO_FILE_EXTENSIONS = ['wav', 'mp3', 'm4a'] as const

export const SUPPORTED_FILE_EXTENSIONS: string[] = [
  ...DOCUMENT_FILE_EXTENSIONS,
  ...IMAGE_FILE_EXTENSIONS,
  ...AUDIO_FILE_EXTENSIONS,
]

export const SUPPORTED_UPLOAD_ACCEPT = SUPPORTED_FILE_EXTENSIONS
  .map((extension) => `.${extension}`)
  .join(',')
