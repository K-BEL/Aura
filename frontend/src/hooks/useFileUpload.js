import { useState, useRef, useCallback } from 'react'

// Supported file types and their MIME patterns
const TEXT_EXTENSIONS = [
  'txt', 'md', 'csv', 'json', 'xml', 'yaml', 'yml', 'toml',
  'js', 'jsx', 'ts', 'tsx', 'py', 'rb', 'go', 'rs', 'java',
  'c', 'cpp', 'h', 'hpp', 'cs', 'swift', 'kt',
  'html', 'css', 'scss', 'less', 'sql', 'sh', 'bash', 'zsh',
  'env', 'gitignore', 'dockerfile', 'makefile', 'log',
]

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB
const MAX_TEXT_LENGTH = 30000 // ~30k chars context limit

function getFileExtension(name) {
  return name.split('.').pop().toLowerCase()
}

function isTextFile(file) {
  const ext = getFileExtension(file.name)
  if (TEXT_EXTENSIONS.includes(ext)) return true
  if (file.type.startsWith('text/')) return true
  if (file.type === 'application/json') return true
  return false
}

async function extractTextFromFile(file) {
  const ext = getFileExtension(file.name)

  // PDF
  if (ext === 'pdf' || file.type === 'application/pdf') {
    return await extractPdfText(file)
  }

  // Text-based files
  if (isTextFile(file)) {
    const text = await file.text()
    return text.slice(0, MAX_TEXT_LENGTH)
  }

  throw new Error(`Unsupported file type: .${ext}`)
}

async function extractPdfText(file) {
  const pdfjsLib = await import('pdfjs-dist')
  
  // Use the bundled worker
  pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.mjs',
    import.meta.url
  ).toString()

  const arrayBuffer = await file.arrayBuffer()
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise
  
  const pages = []
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i)
    const content = await page.getTextContent()
    const text = content.items.map(item => item.str).join(' ')
    pages.push(text)
  }
  
  const fullText = pages.join('\n\n')
  return fullText.slice(0, MAX_TEXT_LENGTH)
}

export function useFileUpload() {
  const [attachedFiles, setAttachedFiles] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const fileInputRef = useRef(null)

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileSelect = useCallback(async (event) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return

    setIsProcessing(true)
    try {
      const processed = []
      for (const file of files) {
        if (file.size > MAX_FILE_SIZE) {
          console.warn(`File too large: ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`)
          continue
        }

        try {
          const text = await extractTextFromFile(file)
          processed.push({
            id: Date.now() + Math.random(),
            name: file.name,
            size: file.size,
            type: getFileExtension(file.name),
            text,
          })
        } catch (err) {
          console.warn(`Skipping unsupported file: ${file.name}`, err)
        }
      }
      setAttachedFiles(prev => [...prev, ...processed])
    } finally {
      setIsProcessing(false)
      // Reset input so the same file can be re-selected
      if (event.target) event.target.value = ''
    }
  }, [])

  const removeFile = useCallback((fileId) => {
    setAttachedFiles(prev => prev.filter(f => f.id !== fileId))
  }, [])

  const clearFiles = useCallback(() => {
    setAttachedFiles([])
  }, [])

  // Build context string to prepend to user message
  const buildFileContext = useCallback(() => {
    if (!attachedFiles.length) return ''
    
    return attachedFiles.map(f => 
      `📎 File: ${f.name}\n\`\`\`\n${f.text}\n\`\`\``
    ).join('\n\n') + '\n\n'
  }, [attachedFiles])

  // Accepted file types for the input
  const acceptTypes = [
    '.pdf',
    ...TEXT_EXTENSIONS.map(ext => `.${ext}`),
    'text/*',
  ].join(',')

  return {
    attachedFiles,
    isProcessing,
    fileInputRef,
    openFilePicker,
    handleFileSelect,
    removeFile,
    clearFiles,
    buildFileContext,
    acceptTypes,
  }
}
