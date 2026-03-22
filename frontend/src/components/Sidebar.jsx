import { Plus, MessageSquare, Trash2, X } from 'lucide-react'

function Sidebar({ conversations, activeId, onSelect, onCreate, onDelete, isOpen, onClose }) {
  const sortedConversations = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt)

  const formatDate = (timestamp) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  return (
    <>
      {/* Backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40"
          onClick={onClose}
        />
      )}

      {/* Sidebar — solid #0f0f0f, separation via subtle right shadow instead of border */}
      <div
        className={`
          fixed z-50 top-0 left-0 h-full w-64
          sidebar-panel
          flex flex-col
          transition-transform duration-300 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        style={{ boxShadow: '1px 0 0 rgba(255,255,255,0.04)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-5">
          <span className="text-[11px] font-semibold uppercase tracking-widest text-white/25">Chats</span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={onCreate}
              className="p-1.5 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/5 transition-all duration-300 ease-in-out"
              title="New Chat"
            >
              <Plus className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/5 transition-all duration-300 ease-in-out"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto scrollbar-hide px-2 space-y-0.5">
          {sortedConversations.length === 0 ? (
            <div className="text-center py-16 px-4">
              <MessageSquare className="w-6 h-6 text-white/10 mx-auto mb-3" />
              <p className="text-white/20 text-xs">No conversations yet</p>
            </div>
          ) : (
            sortedConversations.map(conv => (
              <div
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={`
                  group flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer
                  transition-all duration-300 ease-in-out
                  ${activeId === conv.id
                    ? 'bg-white/8 text-white'
                    : 'text-white/40 hover:bg-white/4 hover:text-white/70'
                  }
                `}
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-60" />
                <div className="flex-1 min-w-0">
                  <p className="text-[13px] truncate leading-snug">{conv.title}</p>
                  <p className="text-[10px] text-white/20 mt-0.5">{formatDate(conv.updatedAt)}</p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete(conv.id); }}
                  className="p-1 rounded-md opacity-0 group-hover:opacity-100 hover:bg-red-500/15 text-white/20 hover:text-red-400 transition-all duration-300 ease-in-out"
                  title="Delete"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        {conversations.length > 0 && (
          <div className="px-4 py-4">
            <p className="text-[10px] text-white/15 text-center">
              {conversations.length} chat{conversations.length !== 1 ? 's' : ''} · stored locally
            </p>
          </div>
        )}
      </div>
    </>
  )
}

export default Sidebar
