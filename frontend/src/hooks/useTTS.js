import { useState, useRef, useEffect } from 'react'
import { TTS_CONFIG } from '../config/tts'

export function useTTS() {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [currentMessageId, setCurrentMessageId] = useState(null)
  const [audioVolume, setAudioVolume] = useState(0)
  const [selectedVoice, setSelectedVoice] = useState(TTS_CONFIG.DEFAULT_VOICE)
  const synthRef = useRef(null) // Fallback SpeechSynthesis
  const audioElementRef = useRef(null)
  const audioContextRef = useRef(null)
  const analyserRef = useRef(null)
  const sourceNodeRef = useRef(null)
  const animationFrameRef = useRef(null)
  const isCurrentlySpeakingRef = useRef(false)
  const useContinueTTSRef = useRef(true) // Try Continue-TTS first

  // Check if Continue-TTS service is available
  const checkTTSService = async () => {
    try {
      console.log(`🔍 Checking Continue-TTS service at: ${TTS_CONFIG.API_URL}`)
      const response = await fetch(`${TTS_CONFIG.API_URL}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(TTS_CONFIG.CONNECTION_TIMEOUT),
        headers: {
          'Content-Type': 'application/json'
        }
      })
      if (response.ok) {
        const data = await response.json()
        useContinueTTSRef.current = data.continue_tts_available === true
        console.log('✅ Continue-TTS service available:', useContinueTTSRef.current)
        if (data.model_loaded) {
          console.log('✅ Model is loaded and ready')
        } else {
          console.warn('⚠️ Model is not loaded yet, but service is available and will load on first request')
        }
      } else {
        useContinueTTSRef.current = false
        console.warn('⚠️ Continue-TTS service returned error, using fallback')
      }
    } catch (error) {
      useContinueTTSRef.current = false
      if (error.name === 'AbortError') {
        console.warn(`⚠️ Continue-TTS service timeout (${TTS_CONFIG.CONNECTION_TIMEOUT}ms), using fallback`)
      } else {
        console.warn('⚠️ Continue-TTS service unavailable, using fallback:', error.message)
      }
      console.log('💡 Tip: Make sure the TTS server is running at:', TTS_CONFIG.API_URL)
    }
  }

  useEffect(() => {
    // Initialize fallback SpeechSynthesis
    synthRef.current = window.speechSynthesis
    
    // Initialize Web Audio API for volume analysis
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext
      if (AudioContext) {
        audioContextRef.current = new AudioContext()
        analyserRef.current = audioContextRef.current.createAnalyser()
        analyserRef.current.fftSize = 256
        analyserRef.current.smoothingTimeConstant = 0.8
      }
    } catch (error) {
      console.warn('Web Audio API not available:', error)
    }
    
    // Check if Continue-TTS API is available
    checkTTSService()
    
    return () => {
      // Cleanup on unmount
      stop()
      if (synthRef.current && synthRef.current.speaking) {
        synthRef.current.cancel()
      }
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
      }
      if (sourceNodeRef.current) {
        sourceNodeRef.current.disconnect()
      }
      if (audioContextRef.current) {
        audioContextRef.current.close()
      }
    }
  }, [])

  // Analyze audio volume in real-time from Web Audio API
  const analyzeVolume = () => {
    if (!analyserRef.current || !isSpeaking || !isCurrentlySpeakingRef.current) {
      setAudioVolume(0)
      return
    }

    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
    analyserRef.current.getByteFrequencyData(dataArray)
    
    // Calculate average volume
    let sum = 0
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i]
    }
    const average = sum / dataArray.length
    const normalizedVolume = average / 255 // Normalize to 0-1
    
    setAudioVolume(normalizedVolume)

    if (isSpeaking && isCurrentlySpeakingRef.current) {
      animationFrameRef.current = requestAnimationFrame(analyzeVolume)
    }
  }
  
  // Generate speech using Continue-TTS API
  const speakWithContinueTTS = async (text, messageId, voice = TTS_CONFIG.DEFAULT_VOICE) => {
    try {
      console.log('🎤 Generating speech with Continue-TTS...')
      
      const response = await fetch(`${TTS_CONFIG.API_URL}/tts/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: text,
          voice: voice
        })
      })
      
      if (!response.ok) {
        throw new Error(`TTS API error: ${response.status}`)
      }

      // Ensure we actually received audio
      const contentType = (response.headers.get('Content-Type') || '').toLowerCase()
      if (!contentType.includes('audio') && !contentType.includes('application/octet-stream')) {
        // Try to surface server error message
        try {
          const maybeJson = await response.clone().json()
          throw new Error(maybeJson.error || 'TTS server did not return audio')
        } catch (_) {
          const text = await response.text()
          throw new Error(text || 'TTS server did not return audio')
        }
      }

      // Get audio blob
      const audioBlob = await response.blob()
      const audioUrl = URL.createObjectURL(audioBlob)
      
      // Create audio element
      const audio = new Audio(audioUrl)
      audioElementRef.current = audio
      
      // Resume audio context if suspended
      if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
        await audioContextRef.current.resume()
      }
      
      // Create audio source and connect to analyser for volume analysis
      const source = audioContextRef.current.createMediaElementSource(audio)
      source.connect(analyserRef.current)
      analyserRef.current.connect(audioContextRef.current.destination)
      sourceNodeRef.current = source
      
      // Set up event handlers
      audio.onplay = () => {
        console.log('🔊 Continue-TTS started playing')
        setIsSpeaking(true)
        setCurrentMessageId(messageId)
        isCurrentlySpeakingRef.current = true
        setAudioVolume(0.5)
        analyzeVolume() // Start volume analysis
      }
      
      audio.onended = () => {
        console.log('🔇 Continue-TTS finished playing')
        isCurrentlySpeakingRef.current = false
        setIsSpeaking(false)
        setCurrentMessageId(null)
        setAudioVolume(0)
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current)
        }
        if (sourceNodeRef.current) {
          sourceNodeRef.current.disconnect()
          sourceNodeRef.current = null
        }
        URL.revokeObjectURL(audioUrl)
      }
      
      audio.onerror = (error) => {
        console.error('Continue-TTS audio error:', error)
        isCurrentlySpeakingRef.current = false
        setIsSpeaking(false)
        setCurrentMessageId(null)
        setAudioVolume(0)
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current)
        }
        URL.revokeObjectURL(audioUrl)
      }
      
      // Play audio
      await audio.play()
      
    } catch (error) {
      console.error('Continue-TTS error:', error)
      // Fallback to browser SpeechSynthesis
      if (TTS_CONFIG.USE_FALLBACK) {
        console.log('🔄 Falling back to browser SpeechSynthesis')
        useContinueTTSRef.current = false
        speakWithFallback(text, messageId)
      } else {
        throw error
      }
    }
  }
  
  // Fallback to browser SpeechSynthesis
  const speakWithFallback = (text, messageId) => {
    if (!text || !synthRef.current) return

    // Resume audio context if suspended
    if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume()
    }

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-US'
    utterance.rate = 1.0
    utterance.pitch = 1.0
    utterance.volume = 1.0

    // Simulate volume since SpeechSynthesis doesn't expose audio stream
    const simulateVolume = () => {
      if (!isCurrentlySpeakingRef.current) {
        return
      }
      
      const time = Date.now() / 100
      const baseVolume = 0.4
      const variation = Math.sin(time) * 0.3 + Math.random() * 0.3
      const volumeSimulation = Math.max(0.1, Math.min(1.0, baseVolume + variation))
      setAudioVolume(volumeSimulation)
    }

    utterance.onstart = () => {
      console.log('🔊 Fallback TTS started speaking')
      setIsSpeaking(true)
      setCurrentMessageId(messageId)
      isCurrentlySpeakingRef.current = true
      setAudioVolume(0.5)
      
      // Update volume every 50ms
      const interval = setInterval(() => {
        if (!isCurrentlySpeakingRef.current) {
          clearInterval(interval)
          return
        }
        simulateVolume()
      }, 50)
      
      // Store interval ID for cleanup
      utterance._volumeInterval = interval
    }

    utterance.onend = () => {
      console.log('🔇 Fallback TTS finished speaking')
      isCurrentlySpeakingRef.current = false
      setIsSpeaking(false)
      setCurrentMessageId(null)
      setAudioVolume(0)
      if (utterance._volumeInterval) {
        clearInterval(utterance._volumeInterval)
      }
    }

    utterance.onerror = (error) => {
      console.error('Speech synthesis error:', error)
      isCurrentlySpeakingRef.current = false
      setIsSpeaking(false)
      setCurrentMessageId(null)
      setAudioVolume(0)
      if (utterance._volumeInterval) {
        clearInterval(utterance._volumeInterval)
      }
    }

    synthRef.current.speak(utterance)
  }

  const speak = (text, messageId, voice = TTS_CONFIG.DEFAULT_VOICE) => {
    // Stop any current speech
    stop()
    
    if (!text) return

    // Try Continue-TTS first, fallback to browser SpeechSynthesis
    if (useContinueTTSRef.current) {
      speakWithContinueTTS(text, messageId, voice)
    } else {
      speakWithFallback(text, messageId)
    }
  }

  const stop = () => {
    // Stop Continue-TTS audio
    if (audioElementRef.current) {
      audioElementRef.current.pause()
      audioElementRef.current.currentTime = 0
      audioElementRef.current = null
    }
    
    // Stop fallback SpeechSynthesis
    if (synthRef.current && synthRef.current.speaking) {
      synthRef.current.cancel()
    }
    
    // Disconnect audio source
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect()
      sourceNodeRef.current = null
    }
    
    isCurrentlySpeakingRef.current = false
    setIsSpeaking(false)
    setCurrentMessageId(null)
    setAudioVolume(0)
    
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }
  }

  return {
    speak,
    stop,
    isSpeaking,
    currentMessageId,
    audioVolume,
    selectedVoice,
    setSelectedVoice,
    voices: TTS_CONFIG.VOICES,
  }
}
