import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout, Card, Form, Input, Button, Select, Space, Typography, message } from 'antd';
import { RocketOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Content } = Layout;
const { Title, Paragraph } = Typography;
const { TextArea } = Input;

export default function HomePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const handleCreateSession = async (values: any) => {
    setLoading(true);
    try {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
      const response = await axios.post(`${apiBaseUrl}/api/sessions`, {
        user_id: values.userId,
        task_type: values.taskType,
        task_description: values.taskDescription,
      });

      const sessionId = response.data.id;
      message.success('会话创建成功！');
      navigate(`/session/${sessionId}`);
    } catch (error: any) {
      console.error('Failed to create session:', error);
      message.error(error.response?.data?.detail || '创建会话失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Layout style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #05070C 0%, #0F131C 100%)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    }}>
      <Content style={{ padding: '40px', maxWidth: '600px', width: '100%' }}>
        <Space direction="vertical" size={32} style={{ width: '100%' }}>
          {/* Header */}
          <div style={{ textAlign: 'center' }}>
            <RocketOutlined style={{
              fontSize: '48px',
              color: '#38BDF8',
              marginBottom: '16px',
            }} />
            <Title level={2} style={{ color: '#E5E7EB', margin: 0 }}>
              元认知自适应学习系统
            </Title>
            <Paragraph style={{ color: '#9CA3AF', marginTop: '12px', fontSize: '15px' }}>
              基于生成式AI的实时元认知状态识别与干预
            </Paragraph>
          </div>

          {/* Session Creation Form */}
          <Card
            style={{
              background: '#0F131C',
              border: '1px solid #1E2636',
              borderRadius: '12px',
            }}
            bodyStyle={{ padding: '32px' }}
          >
            <Form
              form={form}
              layout="vertical"
              onFinish={handleCreateSession}
              initialValues={{
                taskType: 'subject',
              }}
            >
              <Form.Item
                name="userId"
                label={<span style={{ color: '#E5E7EB' }}>用户ID</span>}
                rules={[{ required: true, message: '请输入用户ID' }]}
              >
                <Input
                  placeholder="请输入您的用户ID"
                  size="large"
                  style={{
                    background: '#161D2B',
                    border: '1px solid #2A3441',
                    color: '#E5E7EB',
                  }}
                />
              </Form.Item>

              <Form.Item
                name="taskType"
                label={<span style={{ color: '#E5E7EB' }}>任务类型</span>}
                rules={[{ required: true }]}
              >
                <Select
                  size="large"
                  style={{
                    background: '#161D2B',
                  }}
                  options={[
                    { value: 'subject', label: '学科任务' },
                    { value: 'writing', label: '写作任务' },
                    { value: 'problem_solving', label: '问题解决' },
                  ]}
                />
              </Form.Item>

              <Form.Item
                name="taskDescription"
                label={<span style={{ color: '#E5E7EB' }}>任务描述（可选）</span>}
              >
                <TextArea
                  placeholder="简要描述您的学习任务..."
                  rows={4}
                  style={{
                    background: '#161D2B',
                    border: '1px solid #2A3441',
                    color: '#E5E7EB',
                  }}
                />
              </Form.Item>

              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  size="large"
                  loading={loading}
                  block
                  style={{
                    background: '#38BDF8',
                    borderColor: '#38BDF8',
                    height: '48px',
                    fontSize: '16px',
                    fontWeight: 500,
                  }}
                >
                  开始学习会话
                </Button>
              </Form.Item>
            </Form>
          </Card>

          {/* Info */}
          <Card
            size="small"
            style={{
              background: '#0F131C',
              border: '1px solid #1E2636',
              borderRadius: '12px',
            }}
          >
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Paragraph style={{ color: '#9CA3AF', margin: 0, fontSize: '13px' }}>
                ✨ 系统将实时监测您的元认知状态（Planning, Monitoring, Evaluation）
              </Paragraph>
              <Paragraph style={{ color: '#9CA3AF', margin: 0, fontSize: '13px' }}>
                🎯 在关键时刻提供自适应干预，优化学习过程
              </Paragraph>
              <Paragraph style={{ color: '#9CA3AF', margin: 0, fontSize: '13px' }}>
                📊 可视化展示您的元认知状态变化趋势
              </Paragraph>
            </Space>
          </Card>
        </Space>
      </Content>
    </Layout>
  );
}
