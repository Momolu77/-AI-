import { useState, useRef } from 'react';
import { Layout, Row, Col, Card, Button, Space, Upload, Input, message } from 'antd';
import { PaperClipOutlined, SendOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd';
import ActionLog from './ActionLog';
import WorkEditor from './WorkEditor';
import StateVisualization from './StateVisualization';
import ChatInterface from './ChatInterface';
import type { MetacogState } from '../types';

const { Content } = Layout;
const { TextArea } = Input;

interface WorkspaceLayoutProps {
  sessionId: string;
  isConnected: boolean;
  currentState: MetacogState | null;
  stateHistory: MetacogState[];
  onSendMessage: (content: string) => void;
  onSendEvent: (eventType: string, content: any) => void;
}

export default function WorkspaceLayout({
  sessionId,
  isConnected,
  currentState,
  stateHistory,
  onSendMessage,
  onSendEvent,
}: WorkspaceLayoutProps) {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [inputValue, setInputValue] = useState('');
  const textAreaRef = useRef<any>(null);

  const handleUploadChange = ({ fileList: newFileList }: any) => {
    setFileList(newFileList);
    if (newFileList.length > 0) {
      onSendEvent('attach_file', {
        files: newFileList.map((f: UploadFile) => ({
          name: f.name,
          size: f.size,
        })),
      });
    }
  };

  const handleSend = () => {
    if (!inputValue.trim()) {
      message.warning('请输入内容');
      return;
    }

    // 在对话区显示用户消息
    (window as any).__chatInterface?.addUserMessage(inputValue);

    // 记录 prompt 行为到左栏日志
    window.dispatchEvent(
      new CustomEvent('action_log', {
        detail: { type: 'prompt', content: inputValue },
      })
    );

    onSendMessage(inputValue);
    setInputValue('');
    setFileList([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Layout style={{ height: '100vh', background: '#05070C' }}>
      <Content style={{ padding: '16px', height: '100%' }}>
        <Row gutter={12} style={{ height: '100%' }}>
          {/* 左栏：行为记录 */}
          <Col span={5} style={{ height: '100%' }}>
            <Card
              title={
                <Space>
                  <span style={{ fontSize: '14px', fontWeight: 600 }}>
                    行为日志
                  </span>
                </Space>
              }
              style={{
                height: '100%',
                background: '#0A0D12',
                border: '1px solid #1E2636',
                borderRadius: '12px',
              }}
              bodyStyle={{
                padding: '12px',
                height: 'calc(100% - 57px)',
                overflowY: 'auto',
              }}
              headStyle={{
                borderBottom: '1px solid #1E2636',
                color: '#E5E7EB',
              }}
            >
              <ActionLog sessionId={sessionId} />
            </Card>
          </Col>

          {/* 中栏：工作区 */}
          <Col span={14} style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* 上半部分：写作工作区 */}
            <div style={{ flex: 1, minHeight: 0 }}>
              <Card
                title={
                  <Space>
                    <span style={{ fontSize: '14px', fontWeight: 600 }}>
                      学习任务工作区
                    </span>
                  </Space>
                }
                style={{
                  height: '100%',
                  background: '#0A0D12',
                  border: '1px solid #1E2636',
                  borderRadius: '12px',
                }}
                bodyStyle={{
                  padding: '12px',
                  height: 'calc(100% - 57px)',
                  overflowY: 'auto',
                }}
                headStyle={{
                  borderBottom: '1px solid #1E2636',
                  color: '#E5E7EB',
                }}
              >
                <WorkEditor
                  sessionId={sessionId}
                  onContentChange={(content) => {
                    onSendEvent('edit', { content, length: content.length });
                  }}
                />
              </Card>
            </div>

            {/* 下半部分：AI对话 */}
            <div style={{ height: '320px' }}>
              <Card
                title={
                  <Space>
                    <span style={{ fontSize: '14px', fontWeight: 600 }}>
                      AI 协作对话
                    </span>
                  </Space>
                }
                style={{
                  height: '100%',
                  background: '#0A0D12',
                  border: '1px solid #1E2636',
                  borderRadius: '12px',
                }}
                bodyStyle={{
                  padding: 0,
                  height: 'calc(100% - 57px)',
                  display: 'flex',
                  flexDirection: 'column',
                }}
                headStyle={{
                  borderBottom: '1px solid #1E2636',
                  color: '#E5E7EB',
                }}
              >
                {/* 对话消息区 */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
                  <ChatInterface
                    sessionId={sessionId}
                    isConnected={isConnected}
                    onSendMessage={onSendMessage}
                  />
                </div>

                {/* 输入区 */}
                <div
                  style={{
                    borderTop: '1px solid #1E2636',
                    padding: '12px',
                    background: '#0F131C',
                  }}
                >
                  <Space.Compact style={{ width: '100%' }}>
                    <Upload
                      fileList={fileList}
                      onChange={handleUploadChange}
                      beforeUpload={() => false}
                      showUploadList={false}
                    >
                      <Button
                        icon={<PaperClipOutlined />}
                        style={{
                          background: '#1E2636',
                          border: 'none',
                          color: '#9CA3AF',
                        }}
                      >
                        {fileList.length > 0 ? `${fileList.length} 个文件` : '附件'}
                      </Button>
                    </Upload>
                    <TextArea
                      ref={textAreaRef}
                      value={inputValue}
                      onChange={(e) => setInputValue(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="输入消息... (Shift+Enter 换行)"
                      autoSize={{ minRows: 1, maxRows: 3 }}
                      style={{
                        background: '#161D2B',
                        border: 'none',
                        color: '#E5E7EB',
                        resize: 'none',
                      }}
                    />
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      onClick={handleSend}
                      disabled={!isConnected}
                      style={{
                        background: isConnected ? '#38BDF8' : '#1E2636',
                        border: 'none',
                      }}
                    >
                      发送
                    </Button>
                  </Space.Compact>
                </div>
              </Card>
            </div>
          </Col>

          {/* 右栏：元认知状态监测 */}
          <Col span={5} style={{ height: '100%' }}>
            <Card
              style={{
                height: '100%',
                background: '#0A0D12',
                border: '1px solid #1E2636',
                borderRadius: '12px',
              }}
              bodyStyle={{
                padding: 0,
                height: '100%',
              }}
            >
              <StateVisualization
                currentState={currentState}
                stateHistory={stateHistory}
              />
            </Card>
          </Col>
        </Row>
      </Content>
    </Layout>
  );
}
