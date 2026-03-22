import { useState, useEffect, useRef } from 'react'
import { useChatModel } from '../hooks/useChatModel'
import { useTTS } from '../hooks/useTTS'
import { useASR } from '../hooks/useASR'
import { useFileUpload } from '../hooks/useFileUpload'
import { parseMarkdown } from '../utils/markdown'
import { PROVIDERS, MODELS } from '../config/models'
import { useMarketSearch } from '../hooks/useMarketSearch'
import { 
  Settings, Mic, MicOff, MessageSquare, Image as ImageIcon, Paperclip, 
  Send, User, Bot, Code, FileText, Pause, Menu, Loader2, X,
  Search, Database, Globe
} from 'lucide-react'

// Provider accent colors (minimal — only used for a tiny dot indicator)
const brandAccents = {
  groq: '#f97316',
  openai: '#10b981',
  anthropic: '#f59e0b',
  local: '#60a5fa'
}

function ChatBox({ mode, onModeChange, activeConversation, onMessagesChange, onFirstMessage, onToggleSidebar }) {
  const [input, setInput] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [localModels, setLocalModels] = useState(MODELS.local || [])
  const [showMarketUI, setShowMarketUI] = useState(false)
  
  // Aura Market Search hook
  const {
    search,
    isSearching,
    searchResults,
    triggerScrape,
    isScraping,
    scrapeStatus,
    scrapeAndAnswer,
    isScrapeAnswering,
  } = useMarketSearch()

  const {
    messages,
    sendMessage,
    appendMessage,
    loadMessages,
    isLoading,
    activeProvider,
    setActiveProvider,
    activeModel,
    setActiveModel,
  } = useChatModel('groq', 'llama-3.3-70b-versatile', {
    initialMessages: activeConversation?.messages || [],
    onMessagesChange,
  })

  // Load messages when switching conversations
  const prevConvIdRef = useRef(activeConversation?.id)
  useEffect(() => {
    if (activeConversation?.id !== prevConvIdRef.current) {
      prevConvIdRef.current = activeConversation?.id
      loadMessages(activeConversation?.messages || [])
    }
  }, [activeConversation?.id, activeConversation?.messages, loadMessages])
  
  const { speak, stop, isSpeaking, currentMessageId, selectedVoice, setSelectedVoice, voices } = useTTS()
  const { isRecording, isTranscribing, startRecording, stopAndTranscribe } = useASR()
  const {
    attachedFiles, isProcessing, fileInputRef, openFilePicker,
    handleFileSelect, removeFile, clearFiles, buildFileContext, acceptTypes
  } = useFileUpload()
  const messagesEndRef = useRef(null)
  const isVoiceMode = mode === 'voice'
  const autoPlayRef = useRef(isVoiceMode)
  const textareaRef = useRef(null)

  // Fetch local models
  useEffect(() => {
    const fetchLocalModels = async () => {
      try {
        const response = await fetch('http://localhost:11434/api/tags');
        if (response.ok) {
          const data = await response.json();
          if (data.models && data.models.length > 0) {
            setLocalModels(data.models.map(m => ({ id: m.name, name: `${m.name} (Local)` })));
          }
        }
      } catch (err) {
        console.warn('Could not fetch local models from Ollama:', err);
      }
    };
    fetchLocalModels();
  }, [])

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Voice effect sync
  useEffect(() => {
    autoPlayRef.current = isVoiceMode
  }, [isVoiceMode])

  useEffect(() => {
    if (isVoiceMode && messages.length > 0) {
      const lastMessage = messages[messages.length - 1]
      if (lastMessage.role === 'assistant' && autoPlayRef.current && !isLoading) {
        const messageId = messages.length - 1
        const timeoutId = setTimeout(() => {
          speak(lastMessage.content, messageId, selectedVoice)
        }, 300)
        return () => clearTimeout(timeoutId)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, isLoading, isVoiceMode])

  // Textarea auto-resize
  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
    }
  }

  useEffect(() => {
    adjustTextareaHeight()
  }, [input])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if ((input.trim() || attachedFiles.length) && !isLoading && !isSearching && !isScraping && !isScrapeAnswering) {
      stop()
      // Auto-create conversation on first message
      if (!activeConversation) {
        onFirstMessage()
      }
      
      const userText = input.trim()
      
      // Handle Aura CLI-like commands directly from chat
      if (userText.startsWith('Search market:')) {
        const query = userText.replace('Search market:', '').trim()
        if (query) {
          await sendMessage(`*Searching market data for:* "${query}"`, { skipCompletion: true })
          setInput('')
          await search(query)
          return
        }
      } else if (userText.startsWith('Scrape config:')) {
        const configName = userText.replace('Scrape config:', '').trim()
        if (configName) {
          await sendMessage(`*Triggering scrape job for config:* \`${configName}\``, { skipCompletion: true })
          setInput('')
          await triggerScrape(configName)
          return
        }
      } else if (/^Ask site:/i.test(userText)) {
        const rest = userText.replace(/^Ask site:\s*/i, '').trim()
        const pipeIdx = rest.indexOf('|')
        if (pipeIdx === -1 || !rest.slice(0, pipeIdx).trim() || !rest.slice(pipeIdx + 1).trim()) {
          appendMessage({
            role: 'assistant',
            content:
              'Use **Ask site:** like this:\n\n`Ask site: example_site | What themes do these quotes explore?`\n\nReplace `example_site` with your YAML config name (file name without `.yaml`).',
          })
          setInput('')
          return
        }
        const configName = rest.slice(0, pipeIdx).trim()
        const question = rest.slice(pipeIdx + 1).trim()
        if (!activeConversation) {
          onFirstMessage()
        }
        await sendMessage(
          `**${question}**\n\n_(fresh scrape, config \`${configName}\`)_`,
          { skipCompletion: true },
        )
        setInput('')
        clearFiles()
        if (textareaRef.current) {
          textareaRef.current.style.height = 'auto'
        }
        try {
          const data = await scrapeAndAnswer(configName, question)
          if (data?.answer) {
            appendMessage({ role: 'assistant', content: data.answer })
          }
        } catch (err) {
          appendMessage({
            role: 'assistant',
            content: `❌ **Scrape & answer failed:** ${err.message}`,
          })
        }
        return
      }

      // Prepend file context if files are attached
      const fileCtx = buildFileContext()
      const fullMessage = fileCtx + input
      sendMessage(fullMessage)
      setInput('')
      clearFiles()
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleSpeak = (content, messageId) => {
    if (isSpeaking && currentMessageId === messageId) {
      stop()
    } else {
      speak(content, messageId, selectedVoice)
    }
  }

  const toggleMode = () => {
    const newMode = mode === 'text' ? 'voice' : 'text'
    onModeChange(newMode)
    if (newMode === 'text') stop()
  }

  const handleProviderChange = (e) => {
    const provider = e.target.value
    setActiveProvider(provider)
    const providerModels = provider === 'local' ? localModels : MODELS[provider]
    if (providerModels && providerModels.length > 0) {
      setActiveModel(providerModels[0].id)
    }
  }

  const providerStyle = brandAccents[activeProvider] || '#6366f1'

  const quickStartCards = [
    { icon: <Search className="w-5 h-5"/>, title: "Market Search", desc: "Find listings & trends", action: "Search market: " },
    { icon: <Globe className="w-5 h-5"/>, title: "Ask a site", desc: "Scrape, then answer from that page", action: "Ask site: example_site | " },
    { icon: <Database className="w-5 h-5"/>, title: "Scrape Site", desc: "Trigger data extraction", action: "Scrape config: " },
    { icon: <Code className="w-5 h-5"/>, title: "Chat", desc: "Standard AI assistant", action: "I need help with: " },
  ]

  const activeModelsList = activeProvider === 'local' ? localModels : MODELS[activeProvider]

  return (
    <div className="relative flex flex-col items-center justify-between w-full max-w-4xl mx-auto h-screen px-4 md:px-8 overflow-hidden">
      {/* No glow div — pure black bg */}

      {/* Top nav — floating glass pill, center-aligned */}
      <div className="relative z-20 w-full flex flex-col items-center mt-2">
        <div className="glass-panel flex items-center justify-between gap-4 px-4 py-2 rounded-full transition-all duration-300 ease-in-out shadow-lg" style={{ boxShadow: '0 0 0 1px rgba(255,255,255,0.06)' }}>
          <div className="flex items-center gap-2 border-r border-white/8 pr-4">
            <button
              onClick={onToggleSidebar}
              className="flex items-center justify-center w-8 h-8 rounded-full text-white/30 hover:text-white/70 hover:bg-white/5 transition-all duration-300 ease-in-out"
              title="Toggle sidebar"
            >
              <Menu className="w-4 h-4" />
            </button>
            {/* Tiny accent dot */}
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: brandAccents[activeProvider] || '#6366f1', opacity: 0.7 }}
            />
            <span className="font-medium text-sm text-white/60">
              {PROVIDERS[activeProvider]?.name}
            </span>
          </div>

          <button 
            onClick={() => setShowSettings(!showSettings)}
            className="flex items-center gap-2 hover:bg-white/5 px-3 py-1.5 rounded-full transition-all duration-300 ease-in-out text-sm text-white/40 hover:text-white/70"
          >
            <span className="truncate max-w-[150px] md:max-w-xs">{activeModelsList?.find(m => m.id === activeModel)?.name || 'Select Model'}</span>
            <Settings className={`w-3.5 h-3.5 transition-transform duration-300 ease-in-out ${showSettings ? 'rotate-90' : ''}`} />
          </button>
        </div>

        {/* Retractable Settings Menu */}
        <div className={`mt-4 absolute top-14 left-1/2 -translate-x-1/2 glass-panel p-5 rounded-2xl w-[90%] md:w-[600px] transition-all duration-300 origin-top transform ${showSettings ? 'scale-100 opacity-100 translate-y-0' : 'scale-95 opacity-0 -translate-y-4 pointer-events-none'}`}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="flex flex-col space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-gray-400">Provider</label>
              <select 
                value={activeProvider} 
                onChange={handleProviderChange}
                className="bg-black/50 border border-white/10 text-gray-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-emerald-500/50 appearance-none transition-all cursor-pointer"
              >
                {Object.values(PROVIDERS).map(provider => (
                  <option key={provider.id} value={provider.id}>{provider.name}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-gray-400">Model</label>
              <select 
                value={activeModel} 
                onChange={(e) => setActiveModel(e.target.value)}
                className="bg-black/50 border border-white/10 text-gray-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-emerald-500/50 appearance-none transition-all cursor-pointer"
              >
                {activeModelsList?.map(model => (
                  <option key={model.id} value={model.id}>{model.name}</option>
                ))}
              </select>
            </div>
            <div className="flex flex-col space-y-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-gray-400">Voice</label>
              <select 
                value={selectedVoice} 
                onChange={(e) => setSelectedVoice(e.target.value)}
                className="bg-black/50 border border-white/10 text-gray-200 rounded-xl px-4 py-3 outline-none focus:ring-2 focus:ring-amber-500/50 appearance-none transition-all cursor-pointer"
              >
                {voices.map(voice => (
                  <option key={voice.id} value={voice.id}>{voice.name} ({voice.gender})</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 w-full overflow-y-auto scrollbar-hide my-6 pb-32">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center pt-10">
            {/* Gemini-style sparkle avatar */}
            <div className="relative mb-10">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <Bot className="w-7 h-7 text-white/30" />
              </div>
            </div>
            <h2 className="text-[28px] font-semibold text-white/80 mb-2 tracking-tight">
              How can I help you?
            </h2>
            <p className="text-white/25 text-sm mb-12">Start typing or pick an option below.</p>
            
            <div className="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-4 gap-3 w-full">
              {quickStartCards.map((card, i) => (
                <button 
                  key={i} 
                  onClick={() => setInput(card.action)}
                  className="flex flex-col items-start p-4 rounded-2xl border border-white/5 hover:border-white/10 hover:bg-white/4 transition-all duration-300 ease-in-out text-left group"
                  style={{ background: 'rgba(255,255,255,0.02)' }}
                >
                  <div className="mb-3 text-white/25 group-hover:text-white/50 transition-colors duration-300 ease-in-out">
                    {card.icon}
                  </div>
                  <h3 className="text-white/70 text-sm font-medium mb-1">{card.title}</h3>
                  <p className="text-white/25 text-xs leading-relaxed">{card.desc}</p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-8">
            {messages.map((message, index) => (
              <div key={index} className={`flex w-full message-enter ${
                message.role === 'user' ? 'justify-end' : 'justify-start'
              }`}>
                {/* AI avatar */}
                {message.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0 mr-3 mt-1" style={{ background: 'rgba(255,255,255,0.05)' }}>
                    <Bot className="w-3.5 h-3.5 text-white/40" />
                  </div>
                )}
                
                {message.role === 'user' ? (
                  /* User bubble — soft dark box */
                  <div className="max-w-[75%] px-4 py-3 rounded-3xl group" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <div
                      className="prose prose-invert max-w-none text-[#cccccc] text-[15px]"
                      style={{ lineHeight: 1.6 }}
                      dangerouslySetInnerHTML={{ __html: parseMarkdown(message.content) }}
                    />
                  </div>
                ) : (
                  /* AI response — bare text, no bubble */
                  <div className="flex-1 max-w-[92%] group">
                    <div
                      className="prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-black/40 prose-pre:border prose-pre:border-white/8 text-[#ffffff] text-[15px]"
                      style={{ lineHeight: 1.6 }}
                      dangerouslySetInnerHTML={{ __html: parseMarkdown(message.content) }}
                    />
                    <div className="mt-2 flex options-bar opacity-0 group-hover:opacity-100 transition-opacity duration-300 ease-in-out">
                      <button 
                        onClick={() => handleSpeak(message.content, index)}
                        className={`p-1.5 rounded-lg flex items-center gap-1.5 text-xs transition-all duration-300 ease-in-out ${
                          isSpeaking && currentMessageId === index 
                            ? 'text-amber-400' 
                            : 'text-white/20 hover:text-white/60'
                        }`}
                      >
                        {isSpeaking && currentMessageId === index ? <><Pause className="w-3 h-3"/> Stop</> : <><Mic className="w-3 h-3"/> Read</>}
                      </button>
                    </div>
                  </div>
                )}

                {/* User avatar */}
                {message.role === 'user' && (
                  <div className="w-7 h-7 rounded-xl shrink-0 ml-3 mt-1 flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.08)' }}>
                    <User className="w-3.5 h-3.5 text-white/50" />
                  </div>
                )}
              </div>
            ))}
            
            {/* Gemini shimmer loading */}
            {isLoading && (
              <div className="flex w-full justify-start message-enter">
                <div className="w-7 h-7 rounded-xl shrink-0 mr-3 mt-1 flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.05)' }}>
                  <Bot className="w-3.5 h-3.5 text-white/30" />
                </div>
                <div className="gemini-shimmer w-48 h-5 mt-2" />
              </div>
            )}

            {/* Aura Market Search Results */}
            {searchResults.length > 0 && !isSearching && (
              <div className="flex w-full justify-start message-enter">
                <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0 mr-3 mt-1" style={{ background: 'rgba(255,153,0,0.1)' }}>
                  <Database className="w-3.5 h-3.5 text-orange-400" />
                </div>
                <div className="flex-1 max-w-[92%]">
                  <div className="text-sm font-semibold text-orange-400 mb-3">Market Intelligence Results</div>
                  <div className="grid grid-cols-1 gap-3 w-[80%]">
                    {searchResults.map((res, i) => (
                      <div key={i} className="p-4 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 transition-colors">
                        <div className="flex justify-between items-start mb-2">
                          <h4 className="text-white/90 font-medium text-[15px]">{res.title}</h4>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${
                            res.sentiment === 'positive' ? 'border-green-500/30 text-green-400 bg-green-500/10' :
                            res.sentiment === 'negative' ? 'border-red-500/30 text-red-400 bg-red-500/10' :
                            'border-gray-500/30 text-gray-400 bg-gray-500/10'
                          }`}>
                            {res.sentiment}
                          </span>
                        </div>
                        <p className="text-white/60 text-sm leading-relaxed mb-3">{res.summary}</p>
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {res.entities?.map((ent, j) => (
                            <span key={j} className="text-[11px] px-1.5 py-0.5 rounded bg-white/10 text-white/50">{ent}</span>
                          ))}
                        </div>
                        <div className="flex justify-between items-center text-[11px] text-white/40">
                          <span>Match Score: {(res.score * 100).toFixed(1)}%</span>
                          {res.source_url && (
                            <a href={res.source_url} target="_blank" rel="noreferrer" className="text-orange-400/80 hover:text-orange-400 underline">
                              View Source
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Scrape then answer (in progress) */}
            {isScrapeAnswering && (
              <div className="flex w-full justify-start message-enter">
                <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0 mr-3 mt-1" style={{ background: 'rgba(96,165,250,0.12)' }}>
                  <Loader2 className="w-3.5 h-3.5 text-sky-400 animate-spin" />
                </div>
                <div className="flex-1 max-w-[92%]">
                  <div className="text-sm font-medium text-sky-400/90 mt-1">
                    Scraping the configured site and building an answer from fresh data…
                  </div>
                  <div className="text-xs text-white/35 mt-1">This uses your Aura LLM (e.g. Ollama) on the API host, not the chat model above.</div>
                </div>
              </div>
            )}

            {/* Aura Scrape Status */}
            {(isScraping || scrapeStatus) && (
              <div className="flex w-full justify-start message-enter">
                <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0 mr-3 mt-1" style={{ background: 'rgba(255,153,0,0.1)' }}>
                  {isScraping ? <Loader2 className="w-3.5 h-3.5 text-orange-400 animate-spin" /> : <Database className="w-3.5 h-3.5 text-orange-400" />}
                </div>
                <div className="flex-1 max-w-[92%]">
                  {isScraping ? (
                    <div className="text-sm font-medium text-orange-400 mt-1">Extracting & Enriching data...</div>
                  ) : (
                    <div className="p-4 rounded-xl border border-green-500/20 bg-green-500/5 w-[60%]">
                      <h4 className="text-green-400 font-medium mb-2">Scrape Job Complete ✅</h4>
                      <ul className="text-sm text-white/70 space-y-1">
                        <li>Site: <span className="text-white/90">{scrapeStatus?.site_name}</span></li>
                        <li>Items Scraped: <span className="text-white/90">{scrapeStatus?.items_scraped}</span></li>
                        <li>Items Enriched (LLM): <span className="text-white/90">{scrapeStatus?.items_enriched}</span></li>
                        <li>Items Indexed (ES): <span className="text-white/90">{scrapeStatus?.items_indexed}</span></li>
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

          </div>
        )}
      </div>

      {/* Input area */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 w-[95%] md:w-[720px] z-30">
        <form onSubmit={handleSubmit} className="relative w-full">
          <div
            className="gemini-input-focus flex items-end gap-3 p-2 pl-4 rounded-3xl transition-all duration-300 ease-in-out"
            style={{
              background: 'rgba(30, 30, 30, 0.7)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              border: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            
            {/* Left icons — monochrome */}
            <div className="flex gap-1 pb-1">
              <button type="button" onClick={openFilePicker} disabled={isProcessing} className="p-2 rounded-full text-white/30 hover:text-white/70 transition-all duration-300 ease-in-out">
                {isProcessing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
              </button>
              <button type="button" className="p-2 rounded-full text-white/30 hover:text-white/70 transition-all duration-300 ease-in-out hidden sm:block">
                <ImageIcon className="w-4 h-4" />
              </button>
            </div>

            {/* Attached files + textarea wrapper */}
            <div className="flex-1 flex flex-col">
              {/* File chips */}
              {attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-2 pb-1">
                  {attachedFiles.map(file => (
                    <span key={file.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-500/15 text-indigo-300 text-xs border border-indigo-500/20">
                      <FileText className="w-3 h-3" />
                      <span className="max-w-[120px] truncate">{file.name}</span>
                      <button
                        type="button"
                        onClick={() => removeFile(file.id)}
                        className="p-0.5 rounded-full hover:bg-white/10 transition-colors"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}

              <textarea
                ref={textareaRef}
                className="w-full bg-transparent border-none outline-none text-[15px] resize-none py-3 min-h-[44px] max-h-[150px] scrollbar-hide"
                style={{ color: '#cccccc', lineHeight: 1.6 }}
                placeholder={attachedFiles.length ? 'Ask about the attached file(s)...' : 'Message...'}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSubmit(e)
                  }
                }}
                disabled={isLoading || isScrapeAnswering}
                rows={1}
              />
            </div>

            <div className="flex items-center gap-2 pb-1 pr-1">
              {/* Mic → Transcribe button */}
              <button 
                type="button" 
                onClick={async () => {
                  if (isRecording) {
                    try {
                      const text = await stopAndTranscribe()
                      if (text) setInput(prev => prev ? prev + ' ' + text : text)
                    } catch (err) {
                      console.error('ASR failed:', err)
                    }
                  } else {
                    try {
                      await startRecording()
                    } catch (err) {
                      console.error('Mic failed:', err)
                    }
                  }
                }}
                disabled={isTranscribing}
                className={`p-2 rounded-full transition-all duration-300 ease-in-out ${
                  isRecording 
                    ? 'text-red-400 animate-pulse' 
                    : isTranscribing
                    ? 'text-amber-400 cursor-wait'
                    : 'text-white/30 hover:text-white/70'
                }`}
                title={isRecording ? 'Stop recording' : isTranscribing ? 'Transcribing...' : 'Record voice'}
              >
                {isTranscribing 
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : isRecording 
                  ? <MicOff className="w-4 h-4" /> 
                  : <Mic className="w-4 h-4" />
                }
              </button>

              <button 
                type="button" 
                onClick={toggleMode}
                className={`p-2 rounded-full transition-all duration-300 ease-in-out ${
                  mode === 'voice' 
                    ? 'text-violet-400' 
                    : 'text-white/30 hover:text-white/70'
                }`}
                title="Voice Mode"
              >
                {mode === 'voice' ? <Mic className="w-4 h-4 animate-pulse" /> : <MessageSquare className="w-4 h-4" />}
              </button>
              <button
                type="submit"
                disabled={(!input.trim() && !attachedFiles.length) || isLoading || isScrapeAnswering}
                className={`p-2.5 rounded-full transition-all duration-300 ease-in-out ${
                  (!input.trim() && !attachedFiles.length) || isLoading || isScrapeAnswering
                    ? 'text-white/15 cursor-not-allowed' 
                    : 'bg-white text-black hover:bg-white/90 shadow-lg shadow-white/10'
                }`}
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={acceptTypes}
            onChange={handleFileSelect}
            className="hidden"
          />
          
          <div className="text-center mt-3 text-[11px]" style={{ color: 'rgba(255,255,255,0.18)' }}>
            {PROVIDERS[activeProvider]?.name} · AI can make mistakes.
          </div>
        </form>
      </div>
    </div>
  )
}

export default ChatBox
