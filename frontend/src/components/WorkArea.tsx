import { useState, useRef, useEffect } from 'react';
import { Tabs, Input, Button, Upload, Space, Card, Tag, Alert } from 'antd';
import {
  SendOutlined,
  PaperClipOutlined,
  RobotOutlined,
  UserOutlined,
  EditOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { Message, Intervention } from '../types';

const { TextArea } = Input;

interface WorkAreaProps {
  sessionId: string;
  isConnected: boolean;
  onSendMessage: (content: string) => void;
  onSendEvent: (eventType: string, data: any) => void;
}

export default function WorkArea({
  sessionId,
  isConnected,
  onSendMessage,
  onSendEvent,
}: WorkAreaProps) {
  const [activeTab, setActiveTab] = useState('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [taskContent, setTaskContent] = useState('');
  const [fileList, setFileList] = useState<any[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const taskEditorRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, interventions]);

  // 任务编辑事件记录
  const handleTaskEdit = () => {
    if (taskContent.trim()) {
      (window as any).__actionLogger?.addLog('edit', taskContent.slice(0, 100));
    }
  };

  const handleSend = () => {
    if (!inputValue.trim() || !isConnected) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    // 记录 Prompt 行为
    (window as any).__actionLogger?.addLog('prompt', inputValue.trim());

    setInputValue('');
    setIsLoading(true);

    onSendMessage(inputValue.trim());
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleUpload = (info: any) => {
    setFileList(info.fileList);

    // 记录附件行为
    if (info.file.status === 'done') {
      (window as any).__actionLogger?.addLog(
        'attach',
        `上传文件: ${info.file.name}`
      );
    }
  };

  // Expose methods to parent
  useEffect(() => {
    const aiMessageRef = { content: '', id: '' };

    (window as any).__chatInterface = {
      startAIMessage: () => {
        aiMessageRef.id = Date.now().toString();
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
      },
      appendAIChunk: (chunk: string) => {
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
        setIsLoading(false);
      },
      addAIMessage: (content: string) => {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now().toString(),
            role: 'assistant',
            content,
            timestamp: new Date(),
          },
        ]);
        setIsLoading(false);
      },
      addIntervention: (intervention: Intervention) => {
        setInterventions((prev) => [...prev, intervention]);
      },
    };

    return () => {
      delete (window as any).__chatInterface;
    };
  }, []);

  const tabItems = [
    {
      key: 'task',
      label: (
        <span>
          <EditOutlined /> 任务编辑器
        </span>
      ),
      children: (
        <div
          style={{
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            padding: '20px',
          }}
        >
          <TextArea
            ref={taskEditorRef}
            value={taskContent}
            onChange={(e) => setTaskContent(e.target.value)}
            onBlur={handleTaskEdit}
            placeholder="在此编辑你的学习任务内容..."
            style={{
              flex: 1,
              background: '#0A0D12',
              border: '1px solid #1E2636',
              color: '#E5E7EB',
              fontSize: '14px',
              lineHeight: 1.8,
              resize: 'none',
              fontFamily: 'inherit',
            }}
          />
          <div style={{ marginTop: '12px' }}>
            <Button
              onClick={() => {
                (window as any).__actionLogger?.addLog(
                  'verify',
                  '请求AI审阅当前任务'
                );
                onSendMessage(`请帮我审阅以下内容：\n\n${taskContent}`);
                setActiveTab('chat');
              }}
              disabled={!taskContent.trim()}
              style={{
                background: '#1E2636',
                borderColor: '#38BDF8',
                color: '#38BDF8',
              }}
            >
              请AI审阅
            </Button>
          </div>
        </div>
      ),
    },
    {
      key: 'chat',
      label: (
        <span>
          <RobotOutlined /> AI对话
        </span>
      ),
      children: (
        <div
          style={{
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Messages Area */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}
          >
            {messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: 'flex',
                  justifyContent:
                    msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <Card
                  size="small"
                  style={{
                    maxWidth: '75%',
                    background: msg.role === 'user' ? '#1E2636' : '#0F131C',
                    border:
                      msg.role === 'user'
                        ? '1px solid #38BDF8'
                        : '1px solid #2A3441',
                    borderRadius: '12px',
                  }}
                >
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Space size={8}>
                      {msg.role === 'assistant' ? (
                        <RobotOutlined style={{ color: '#38BDF8' }} />
                      ) : (
                        <UserOutlined style={{ color: '#6EE7B7' }} />
                      )}
                      <span
                        style={{
                          color: '#9CA3AF',
                          fontSize: '12px',
                        }}
                      >
                        {msg.timestamp.toLocaleTimeString('zh-CN', {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    </Space>
                    <div
                      style={{
                        color: '#E5E7EB',
                        lineHeight: 1.6,
                        fontSize: '14px',
                      }}
                    >
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      ) : (
                        <div style={{ whiteSpace: 'pre-wrap' }}>
                          {msg.content}
                        </div>
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
                message={
                  <Space>
                    <span style={{ fontWeight: 600 }}>元认知提示</span>
                    <Tag color="orange">{intervention.type}</Tag>
                  </Space>
                }
                description={
                  <div style={{ marginTop: '8px' }}>
                    <div
                      style={{
                        fontSize: '12px',
                        color: '#9CA3AF',
                        marginBottom: '8px',
                      }}
                    >
                      触发原因: {intervention.reason}
                    </div>
                    <div
                      style={{
                        fontSize: '14px',
                        lineHeight: 1.6,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {intervention.content}
                    </div>
                  </div>
                }
                type="warning"
                showIcon
                style={{
                  background: '#161D2B',
                  border: '1px solid #E9A568',
                  borderRadius: '12px',
                }}
              />
            ))}

            {isLoading && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  color: '#9CA3AF',
                  fontSize: '13px',
                }}
              >
                <RobotOutlined spin />
                <span>AI 正在思考...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div
            style={{
              padding: '16px 20px',
              borderTop: '1px solid #1E2636',
              background: '#0A0D12',
            }}
          >
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Upload
                fileList={fileList}
                onChange={handleUpload}
                beforeUpload={() => false}
                multiple
              >
                <Button
                  icon={<PaperClipOutlined />}
                  size="small"
                  style={{
                    background: '#0F131C',
                    borderColor: '#2A3441',
                    color: '#9CA3AF',
                  }}
                >
                  添加附件
                </Button>
              </Upload>

              <Space.Compact style={{ width: '100%' }}>
                <TextArea
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder="输入消息... (Shift+Enter 换行)"
                  autoSize={{ minRows: 1, maxRows: 4 }}
                  disabled={!isConnected}
                  style={{
                    background: '#0A0D12',
                    border: '1px solid #2A3441',
                    color: '#E5E7EB',
                    borderRadius: '8px 0 0 8px',
                  }}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={handleSend}
                  disabled={!isConnected || !inputValue.trim()}
                  style={{
                    background: '#38BDF8',
                    borderColor: '#38BDF8',
                    borderRadius: '0 8px 8px 0',
                    height: 'auto',
                  }}
                >
                  发送
                </Button>
              </Space.Compact>
            </Space>
          </div>
        </div>
      ),
    },
  ];

  return (
    <Tabs
      activeKey={activeTab}
      onChange={setActiveTab}
      items={tabItems}
      style={{ height: '100%' }}
      tabBarStyle={{
        background: '#0A0D12',
        borderBottom: '1px solid #1E2636',
        margin: 0,
        padding: '0 20px',
      }}
    />
  );
}
