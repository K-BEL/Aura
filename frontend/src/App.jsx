import { useState, useCallback } from 'react'
import { useConversations } from './hooks/useConversations'
import ChatBox from './components/ChatBox'
import Sidebar from './components/Sidebar'
import './App.css'

function App() {
  const [mode, setMode] = useState('text')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const {
    conversations,
    activeConversation,
    activeId,
    createConversation,
    updateMessages,
    deleteConversation,
    selectConversation,
  } = useConversations()

  const handleNewChat = useCallback(() => {
    createConversation()
    setSidebarOpen(false)
  }, [createConversation])

  const handleSelect = useCallback((id) => {
    selectConversation(id)
    setSidebarOpen(false)
  }, [selectConversation])

  const handleMessagesChange = useCallback((messages) => {
    if (activeId && messages.length > 0) {
      updateMessages(activeId, messages)
    }
  }, [activeId, updateMessages])

  // Auto-create a conversation if none exists
  const handleFirstMessage = useCallback(() => {
    if (!activeId) {
      return createConversation()
    }
    return activeId
  }, [activeId, createConversation])

  return (
    <div className="app flex h-screen">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onCreate={handleNewChat}
        onDelete={deleteConversation}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />
      <ChatBox
        mode={mode}
        onModeChange={setMode}
        activeConversation={activeConversation}
        onMessagesChange={handleMessagesChange}
        onFirstMessage={handleFirstMessage}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
      />
    </div>
  )
}

export default App
