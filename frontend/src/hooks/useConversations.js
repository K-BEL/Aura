import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'chat_app_conversations'
const ACTIVE_KEY = 'chat_app_active_conversation'

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

function getTitle(messages) {
  const firstUser = messages.find(m => m.role === 'user')
  if (!firstUser) return 'New Chat'
  const text = firstUser.content.slice(0, 50)
  return text.length < firstUser.content.length ? text + '…' : text
}

function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveConversations(conversations) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations))
}

export function useConversations() {
  const [conversations, setConversations] = useState(() => loadConversations())
  const [activeId, setActiveId] = useState(() => localStorage.getItem(ACTIVE_KEY) || null)

  // Persist to localStorage whenever conversations change
  useEffect(() => {
    saveConversations(conversations)
  }, [conversations])

  // Persist active conversation ID
  useEffect(() => {
    if (activeId) {
      localStorage.setItem(ACTIVE_KEY, activeId)
    } else {
      localStorage.removeItem(ACTIVE_KEY)
    }
  }, [activeId])

  const activeConversation = conversations.find(c => c.id === activeId) || null

  const createConversation = useCallback(() => {
    const newConv = {
      id: generateId(),
      title: 'New Chat',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    setConversations(prev => [newConv, ...prev])
    setActiveId(newConv.id)
    return newConv.id
  }, [])

  const updateMessages = useCallback((conversationId, messages) => {
    setConversations(prev =>
      prev.map(c =>
        c.id === conversationId
          ? { ...c, messages, title: getTitle(messages), updatedAt: Date.now() }
          : c
      )
    )
  }, [])

  const deleteConversation = useCallback((conversationId) => {
    setConversations(prev => prev.filter(c => c.id !== conversationId))
    if (activeId === conversationId) {
      setActiveId(null)
    }
  }, [activeId])

  const selectConversation = useCallback((conversationId) => {
    setActiveId(conversationId)
  }, [])

  const clearAll = useCallback(() => {
    setConversations([])
    setActiveId(null)
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(ACTIVE_KEY)
  }, [])

  return {
    conversations,
    activeConversation,
    activeId,
    createConversation,
    updateMessages,
    deleteConversation,
    selectConversation,
    clearAll,
  }
}
