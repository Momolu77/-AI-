import { useState, useRef, useEffect } from 'react';
import { Card, Space, Alert } from 'antd';
import { RobotOutlined, UserOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { Message, Intervention } from '../types';

interface ChatInterfaceProps {
  sessionId: string;
  isConnected: boolean;
  onSendMessage: (content: string) => void;
}

export default function ChatInterface({
  sessionId,
  isConnected,
  onSendMessage
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, interventions]);

  // Expose methods to parent via global store
  useEffect(() => {
    const aiMessageRef = { content: '', id: '' };

    // 内部：创建一个新的空 AI 消息容器
    const startAIMessage = () => {
      aiMessageRef.id = `ai-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      aiMessageRef.content = '';
      setMessages((prev) => [
        ...prev,
        {
          id: aiMessageRef.id,
          role: 'assistant',
          content: '',
          timestamp: new Date(),
        },
      ]);
      setIsLoading(true);
    };

    (window as any).__chatInterface = {
      startAIMessage,
      appendAIChunk: (chunk: string) => {
        // 首个 chunk 到达时若无活跃流式消息，自动创建（修复多轮对话卡死）
        if (!aiMessageRef.id) {
          startAIMessage();
        }
        aiMessageRef.content += chunk;
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === aiMessageRef.id
              ? { ...msg, content: aiMessageRef.content }
              : msg
          )
        );
      },
      finishAIMessage: () => {
        // 重置活跃流式消息，确保下一轮对话能创建新容器
        aiMessageRef.id = '';
        aiMessageRef.content = '';
        setIsLoading(false);
      },
      addAIMessage: (content: string) => {
        setMessages((prev) => [
          ...prev,
          {
            id: `ai-${Date.now()}`,
            role: 'assistant',
            content,
            timestamp: new Date(),
          },
        ]);
        setIsLoading(false);
      },
      addUserMessage: (content: string) => {
        setMessages((prev) => [
          ...prev,
          {
            id: `user-${Date.now()}`,
            role: 'user',
            content,
            timestamp: new Date(),
          },
        ]);
        setIsLoading(true);
      },
      addIntervention: (intervention: Intervention) => {
        setInterventions((prev) => [...prev, intervention]);
      },
    };

    return () => {
      delete (window as any).__chatInterface;
    };
  }, []);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      gap: '12px',
    }}>
      {messages.map((msg) => (
        <div
          key={msg.id}
          style={{
            display: 'flex',
            justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}
        >
          <Card
            size="small"
            style={{
              maxWidth: '85%',
              background: msg.role === 'user' ? '#1E2636' : '#0F131C',
              border: msg.role === 'user' ? '1px solid #38BDF8' : '1px solid #2A3441',
              borderRadius: '12px',
            }}
            bodyStyle={{ padding: '10px 14px' }}
          >
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Space size={8}>
                {msg.role === 'assistant' ? (
                  <RobotOutlined style={{ color: '#38BDF8', fontSize: '14px' }} />
                ) : (
                  <UserOutlined style={{ color: '#6EE7B7', fontSize: '14px' }} />
                )}
                <span style={{
                  color: '#9CA3AF',
                  fontSize: '11px',
                }}>
                  {msg.timestamp.toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </span>
              </Space>
              <div style={{
                color: '#E5E7EB',
                lineHeight: 1.6,
                fontSize: '13px',
              }}>
                {msg.role === 'assistant' ? (
                  <ReactMarkdown>{msg.content || '...'}</ReactMarkdown>
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                )}
              </div>
            </Space>
          </Card>
        </div>
      ))}

      {/* Interventions */}
      {interventions.map((intervention, idx) => (
        <Alert
          key={idx}
          message="元认知提示"
          description={
            <div style={{ marginTop: '4px', fontSize: '13px' }}>
              {intervention.content}
            </div>
          }
          type="warning"
          showIcon
          style={{
            background: '#161D2B',
            border: '1px solid #E9A568',
            borderRadius: '8px',
          }}
        />
      ))}

      {isLoading && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          color: '#9CA3AF',
          fontSize: '12px',
          padding: '8px',
        }}>
          <RobotOutlined spin />
          <span>AI 正在思考...</span>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
}
