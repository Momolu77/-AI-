import { useRef, useEffect } from 'react'
import { Input, Button, Badge } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { useSessionStore, Message } from '@/store/sessionStore'
import { useState } from 'react'

interface Props {
  onSendMessage: (text: string) => void
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'
  const isIntervention = msg.role === 'intervention'

  if (isIntervention) {
    return (
      <div style={{
        background: 'oklch(97% 0.02 270)',
        border: '1px solid oklch(85% 0.06 270)',
        borderRadius: 10,
        padding: '10px 14px',
        fontSize: 13,
        color: 'oklch(35% 0.12 270)',
        marginBottom: 8,
      }}>
        <span style={{ fontWeight: 600, fontSize: 11, letterSpacing: 0.4, display: 'block', marginBottom: 4 }}>
          💡 学习提示
        </span>
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 8,
    }}>
      <div style={{
        maxWidth: '72%',
        background: isUser ? 'oklch(55% 0.18 264)' : '#fff',
        color: isUser ? '#fff' : 'oklch(20% 0.02 264)',
        border: isUser ? 'none' : '1px solid oklch(92% 0.01 264)',
        borderRadius: isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
        padding: '9px 13px',
        fontSize: 14,
        lineHeight: 1.6,
      }}>
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
    </div>
  )
}

export default function ChatPanel({ onSendMessage }: Props) {
  const messages = useSessionStore(s => s.messages)
  const connected = useSessionStore(s => s.connected)
  const [text, setText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = () => {
    const trimmed = text.trim()
    if (!trimmed) return
    onSendMessage(trimmed)
    setText('')
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      background: '#fff',
      borderRadius: 12,
      border: '1px solid oklch(92% 0.01 264)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid oklch(94% 0.01 264)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 13,
        fontWeight: 600,
        color: 'oklch(25% 0.04 264)',
      }}>
        <Badge status={connected ? 'success' : 'error'} />
        AI 对话区
        <span style={{ fontWeight: 400, color: 'oklch(55% 0.02 264)', marginLeft: 'auto' }}>
          {connected ? '已连接' : '连接中…'}
        </span>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 16, minHeight: 0 }}>
        {messages.length === 0 && (
          <div style={{ color: 'oklch(65% 0.02 264)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>
            开始与 AI 对话，系统将实时监测你的学习过程
          </div>
        )}
        {messages.map((m, i) => <MessageBubble key={i} msg={m} />)}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid oklch(94% 0.01 264)',
        display: 'flex',
        gap: 8,
      }}>
        <Input.TextArea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="输入消息…（Shift+Enter 换行）"
          autoSize={{ minRows: 1, maxRows: 4 }}
          style={{ resize: 'none', fontSize: 14 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={send}
          disabled={!connected || !text.trim()}
          style={{ alignSelf: 'flex-end', height: 36 }}
        />
      </div>
    </div>
  )
}
