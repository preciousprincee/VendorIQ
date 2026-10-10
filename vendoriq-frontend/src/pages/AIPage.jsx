import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Trash2 } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useFeatureAccess } from '../hooks/useFeatureAccess'
import UpgradePrompt from '../components/billing/UpgradePrompt'
import ConfirmDialog from '../components/ConfirmDialog'
import api from '../lib/api'
import { getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

const GREETING = { role: 'assistant', content: `Hello! I'm your VendorIQ assistant. Ask me anything about your store's sales, inventory, or profit — I'll give you straight answers based on your actual data.` }

const SUGGESTIONS = [
  "What's my profit today?",
  "Which products are selling best this month?",
  "What should I restock urgently?",
  "Which products are not moving?",
  "Compare this week's revenue to last week",
  "What's my total stock value?",
]

export default function AIPage() {
  const { activeStore } = useStore()
  const { allowed: aiAllowed } = useFeatureAccess('ai_assistant')
  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [confirmingClear, setConfirmingClear] = useState(false)
  const [clearing, setClearing] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!activeStore) return
    // Same race guard as the other pages - switching stores quickly could
    // let a slower response for the OLD store's chat history land after
    // the new store's history has already loaded, showing the wrong
    // store's conversation.
    let cancelled = false
    const loadHistory = async () => {
      try {
        const { data } = await api.get(`/ai/${activeStore.id}/history/`)
        if (!cancelled && data.messages?.length) setMessages(data.messages)
      } catch (err) {
        // A 404 here just means "no store/no history yet" and is fine to
        // ignore - but any other failure (500, network, auth) means the
        // saved conversation genuinely couldn't be loaded, which looks
        // exactly like "my chat got deleted" if we stay silent about it.
        // Surface that distinction instead of guessing.
        if (!cancelled && err?.response?.status && err.response.status !== 404) {
          toast.error('Could not load your saved conversation. Showing a new chat for now.')
        }
      } finally {
        if (!cancelled) setHistoryLoaded(true)
      }
    }
    loadHistory()
    return () => { cancelled = true }
  }, [activeStore])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text) => {
    const message = text || input.trim()
    if (!message || loading) return

    setInput('')
    setMessages(m => [...m, { role: 'user', content: message }])
    setLoading(true)

    try {
      const { data } = await api.post('/ai/chat/', { message, storeId: activeStore.id })
      setMessages(m => [...m, { role: 'assistant', content: data.reply }])
    } catch (err) {
      toast.error(getErrorMessage(err))
      setMessages(m => [...m, { role: 'assistant', content: 'Sorry, I ran into an error. Try again.' }])
    } finally {
      setLoading(false)
    }
  }

  const handleClearChat = async () => {
    setClearing(true)
    try {
      await api.delete(`/ai/${activeStore.id}/history/`)
      setMessages([GREETING])
      toast.success('Chat cleared')
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setClearing(false)
      setConfirmingClear(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  return (
    <div className="flex flex-col h-full max-h-screen">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-navy-700 flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center">
          <Bot size={17} className="text-brand-600 dark:text-brand-400" />
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-semibold text-slate-text">AI Assistant</h1>
          <p className="text-xs text-slate-dim">{activeStore?.name} · Powered by Groq</p>
        </div>
        {aiAllowed && messages.length > 1 && (
          <button onClick={() => setConfirmingClear(true)} aria-label="Clear chat" className="text-slate-dim hover:text-red-500 dark:hover:text-red-400 transition-colors p-1.5" title="Clear chat">
            <Trash2 size={16} />
          </button>
        )}
      </div>

      <ConfirmDialog
        open={confirmingClear}
        title="Clear this conversation?"
        message="This cannot be undone."
        confirmLabel="Clear"
        loading={clearing}
        onConfirm={handleClearChat}
        onCancel={() => setConfirmingClear(false)}
      />

      {/* Messages */}
      {!aiAllowed ? (
        <div className="flex-1 flex items-center justify-center px-6">
          <UpgradePrompt feature="ai_assistant" />
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto px-4 py-5 space-y-4">
            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${msg.role === 'assistant' ? 'bg-brand-50 dark:bg-brand-500/15' : 'bg-navy-700'}`}>
                  {msg.role === 'assistant'
                    ? <Bot size={14} className="text-brand-600 dark:text-brand-400" />
                    : <User size={14} className="text-slate-muted" />
                  }
                </div>
                <div className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${msg.role === 'assistant' ? 'bg-navy-800 text-slate-text' : 'bg-navy-700 text-slate-text'}`}>
                  {msg.content}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0">
                  <Bot size={14} className="text-brand-600 dark:text-brand-400" />
                </div>
                <div className="bg-navy-800 rounded-xl px-4 py-3 flex gap-1 items-center">
                  {[0,1,2].map(i => (
                    <span key={i} className="w-1.5 h-1.5 bg-brand-500 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 150}ms` }} />
                  ))}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Suggestions */}
          {messages.length <= 1 && (
            <div className="px-4 pb-3 flex gap-2 overflow-x-auto flex-shrink-0">
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => sendMessage(s)}
                  className="flex-shrink-0 text-xs px-3 py-2 bg-navy-800 border border-navy-700 rounded-full text-slate-muted hover:text-slate-text hover:border-brand-500/50 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div className="px-4 py-4 border-t border-navy-700 flex-shrink-0">
            <div className="flex gap-2">
              <textarea
                className="input flex-1 resize-none min-h-[44px] max-h-28 py-3 text-sm"
                placeholder="Ask about your sales, inventory, or profit..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                rows={1}
              />
              <button
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                className="btn-primary flex-shrink-0 px-3 self-end"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="text-xs text-slate-dim mt-2 text-center">Answers are based on your live store data</p>
          </div>
        </>
      )}
    </div>
  )
}
