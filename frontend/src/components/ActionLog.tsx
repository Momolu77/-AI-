import { useState, useEffect } from 'react';
import { Timeline, Tag, Space, Typography } from 'antd';
import {
  SendOutlined,
  EditOutlined,
  CheckCircleOutlined,
  FileAddOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

interface ActionLogProps {
  sessionId: string;
}

interface LogEntry {
  id: string;
  type: 'prompt' | 'edit' | 'verify' | 'attach';
  content: string;
  timestamp: Date;
}

export default function ActionLog({ sessionId }: ActionLogProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    // 监听全局事件并记录到日志
    const handleLogEvent = (event: CustomEvent) => {
      setLogs((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          ...event.detail,
          timestamp: new Date(),
        },
      ]);
    };

    window.addEventListener('action_log' as any, handleLogEvent);

    return () => {
      window.removeEventListener('action_log' as any, handleLogEvent);
    };
  }, []);

  const getIcon = (type: string) => {
    switch (type) {
      case 'prompt':
        return <SendOutlined style={{ color: '#38BDF8' }} />;
      case 'edit':
        return <EditOutlined style={{ color: '#E9A568' }} />;
      case 'verify':
        return <CheckCircleOutlined style={{ color: '#6EE7B7' }} />;
      case 'attach':
        return <FileAddOutlined style={{ color: '#A78BFA' }} />;
      default:
        return null;
    }
  };

  const getLabel = (type: string) => {
    switch (type) {
      case 'prompt':
        return <Tag color="blue">Prompt</Tag>;
      case 'edit':
        return <Tag color="orange">编辑</Tag>;
      case 'verify':
        return <Tag color="green">验证</Tag>;
      case 'attach':
        return <Tag color="purple">附件</Tag>;
      default:
        return null;
    }
  };

  return (
    <div style={{ padding: '8px' }}>
      {logs.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            color: '#6B7280',
            fontSize: '13px',
            marginTop: '40px',
          }}
        >
          等待操作记录...
        </div>
      ) : (
        <Timeline
          items={logs.map((log) => ({
            dot: getIcon(log.type),
            children: (
              <Space direction="vertical" size={4}>
                {getLabel(log.type)}
                <Text
                  style={{
                    color: '#9CA3AF',
                    fontSize: '12px',
                    display: 'block',
                    wordBreak: 'break-word',
                  }}
                  ellipsis={{ tooltip: log.content }}
                >
                  {log.content}
                </Text>
                <Text style={{ color: '#6B7280', fontSize: '11px' }}>
                  {log.timestamp.toLocaleTimeString('zh-CN')}
                </Text>
              </Space>
            ),
          }))}
        />
      )}
    </div>
  );
}
