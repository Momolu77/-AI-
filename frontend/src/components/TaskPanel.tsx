import { useState } from 'react'
import { Input, Button, Select, Typography, Divider } from 'antd'
import { WSIncoming } from '@/types'

const { Text } = Typography

const EVENT_TYPES = [
  { label: '发送 Prompt', value: 'prompt' },
  { label: '编辑内容', value: 'edit' },
  { label: '验证结果', value: 'verify' },
]

interface Props {
  onSendEvent: (e: WSIncoming) => void
}

export default function TaskPanel({ onSendEvent }: Props) {
  const [eventType, setEventType] = useState<WSIncoming['event_type']>('prompt')
  const [content, setContent] = useState('')

  const send = () => {
    const trimmed = content.trim()
    if (!trimmed) return
    onSendEvent({ event_type: eventType, content: trimmed })
    setContent('')
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 12,
      background: '#fff', borderRadius: 12,
      border: '1px solid oklch(92% 0.01 264)',
      padding: 16, overflow: 'hidden',
    }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: 'oklch(25% 0.04 264)' }}>
        学习任务区
      </span>

      <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.6 }}>
        在此记录你的学习操作：发送 Prompt、编辑内容、或验证结果。
        系统将实时分析你的元认知行为。
      </Text>

      <Divider style={{ margin: '4px 0' }} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <Text style={{ fontSize: 12, color: 'oklch(45% 0.02 264)' }}>操作类型</Text>
        <Select
          value={eventType}
          onChange={setEventType}
          options={EVENT_TYPES}
          size="small"
          style={{ width: '100%' }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
        <Text style={{ fontSize: 12, color: 'oklch(45% 0.02 264)' }}>内容</Text>
        <Input.TextArea
          value={content}
          onChange={e => setContent(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder={
            eventType === 'prompt' ? '描述你给 AI 的 Prompt 意图…' :
            eventType === 'edit' ? '描述你修改了什么内容…' :
            '描述你如何验证结果…'
          }
          autoSize={{ minRows: 4, maxRows: 8 }}
          style={{ fontSize: 13, resize: 'none' }}
        />
      </div>

      <Button
        type="primary"
        onClick={send}
        disabled={!content.trim()}
        style={{ width: '100%' }}
      >
        记录操作
      </Button>

      <Divider style={{ margin: '4px 0' }} />

      <div style={{
        background: 'oklch(97% 0.015 264)',
        borderRadius: 8,
        padding: '10px 12px',
        fontSize: 12,
        color: 'oklch(45% 0.04 264)',
        lineHeight: 1.7,
      }}>
        <strong>提示</strong><br />
        • 记录真实的学习操作行为<br />
        • 系统根据操作模式推断元认知状态<br />
        • 必要时会弹出个性化学习提示
      </div>
    </div>
  )
}
