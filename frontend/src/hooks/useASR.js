import { useState, useRef, useCallback } from 'react'
import { TTS_CONFIG } from '../config/tts'

export function useASR() {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm'
      })

      chunksRef.current = []
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorderRef.current = mediaRecorder
      mediaRecorder.start()
      setIsRecording(true)
    } catch (err) {
      console.error('Mic access denied:', err)
      throw new Error('Microphone access denied. Please allow microphone access.')
    }
  }, [])

  const stopRecording = useCallback(() => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current
      if (!recorder || recorder.state === 'inactive') {
        resolve(null)
        return
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        chunksRef.current = []

        // Stop all tracks
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(t => t.stop())
          streamRef.current = null
        }

        setIsRecording(false)
        resolve(blob)
      }

      recorder.stop()
    })
  }, [])

  const transcribe = useCallback(async (audioBlob) => {
    if (!audioBlob) return null

    setIsTranscribing(true)
    try {
      const formData = new FormData()
      formData.append('audio', audioBlob, 'recording.webm')

      const apiUrl = TTS_CONFIG.API_URL
      const response = await fetch(`${apiUrl}/asr/transcribe`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.error || `Transcription failed (${response.status})`)
      }

      const data = await response.json()
      return data.text || ''
    } catch (err) {
      console.error('Transcription error:', err)
      throw err
    } finally {
      setIsTranscribing(false)
    }
  }, [])

  // One-shot: stop recording → transcribe → return text
  const stopAndTranscribe = useCallback(async () => {
    const blob = await stopRecording()
    if (!blob) return ''
    return await transcribe(blob)
  }, [stopRecording, transcribe])

  return {
    isRecording,
    isTranscribing,
    startRecording,
    stopRecording,
    stopAndTranscribe,
    transcribe,
  }
}
