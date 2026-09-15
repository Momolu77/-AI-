import { useState, useRef, useEffect } from 'react';
import { Input, Button, Space, Tag } from 'antd';
import { SaveOutlined, UndoOutlined, RedoOutlined } from '@ant-design/icons';

const { TextArea } = Input;

interface WorkEditorProps {
  sessionId: string;
  onContentChange: (content: string) => void;
}

export default function WorkEditor({ sessionId, onContentChange }: WorkEditorProps) {
  const [content, setContent] = useState('');
  const [wordCount, setWordCount] = useState(0);
  const [history, setHistory] = useState<string[]>(['']);
  const [historyIndex, setHistoryIndex] = useState(0);
  const timerRef = useRef<number>();

  useEffect(() => {
    const count = content.trim().length;
    setWordCount(count);
  }, [content]);

  const handleChange = (value: string) => {
    setContent(value);

    // 防抖：500ms 后记录到历史
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = window.setTimeout(() => {
      setHistory((prev) => [...prev.slice(0, historyIndex + 1), value]);
      setHistoryIndex((prev) => prev + 1);

      // 触发编辑事件
      window.dispatchEvent(
        new CustomEvent('action_log', {
          detail: {
            type: 'edit',
            content: `编辑了 ${value.length - content.length} 个字符`,
          },
        })
      );

      onContentChange(value);
    }, 500);
  };

  const handleUndo = () => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setHistoryIndex(newIndex);
      setContent(history[newIndex]);
    }
  };

  const handleRedo = () => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      setContent(history[newIndex]);
    }
  };

  const handleSave = () => {
    window.dispatchEvent(
      new CustomEvent('action_log', {
        detail: {
          type: 'verify',
          content: `保存了 ${wordCount} 个字符`,
        },
      })
    );
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 工具栏 */}
      <Space
        style={{
          marginBottom: '12px',
          padding: '8px',
          background: '#0F131C',
          borderRadius: '8px',
          justifyContent: 'space-between',
          width: '100%',
        }}
      >
        <Space>
          <Button
            icon={<UndoOutlined />}
            size="small"
            disabled={historyIndex <= 0}
            onClick={handleUndo}
            style={{ background: '#1E2636', border: 'none', color: '#9CA3AF' }}
          >
            撤销
          </Button>
          <Button
            icon={<RedoOutlined />}
            size="small"
            disabled={historyIndex >= history.length - 1}
            onClick={handleRedo}
            style={{ background: '#1E2636', border: 'none', color: '#9CA3AF' }}
          >
            重做
          </Button>
        </Space>

        <Space>
          <Tag color="blue" style={{ margin: 0 }}>
            {wordCount} 字
          </Tag>
          <Button
            icon={<SaveOutlined />}
            size="small"
            type="primary"
            onClick={handleSave}
            style={{ background: '#38BDF8', border: 'none' }}
          >
            保存
          </Button>
        </Space>
      </Space>

      {/* 编辑区 */}
      <TextArea
        value={content}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="在这里开始你的学习任务..."
        style={{
          flex: 1,
          background: '#161D2B',
          border: '1px solid #1E2636',
          borderRadius: '8px',
          color: '#E5E7EB',
          fontSize: '14px',
          lineHeight: 1.6,
          resize: 'none',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}
        onFocus={(e) => {
          e.target.style.borderColor = '#38BDF8';
        }}
        onBlur={(e) => {
          e.target.style.borderColor = '#1E2636';
        }}
      />
    </div>
  );
}
