import { Card, Progress, Space, Typography, Tag } from 'antd';
import { Line } from '@ant-design/charts';
import type { MetacogState } from '../types';

const { Title, Text } = Typography;

interface MetacogMonitorProps {
  currentState: MetacogState | null;
  stateHistory: MetacogState[];
}

export default function MetacogMonitor({
  currentState,
  stateHistory,
}: MetacogMonitorProps) {
  const getStateColor = (value: number) => {
    if (value >= 0.7) return '#6EE7B7';
    if (value >= 0.4) return '#E9A568';
    return '#EF4444';
  };

  const getConfidenceColor = (value: number) => {
    if (value >= 0.8) return 'success';
    if (value >= 0.5) return 'warning';
    return 'error';
  };

  const chartData = stateHistory.flatMap((state, index) => [
    { time: index, dimension: 'Planning', value: state.planning },
    { time: index, dimension: 'Monitoring', value: state.monitoring },
    { time: index, dimension: 'Evaluation', value: state.evaluation },
  ]);

  const chartConfig = {
    data: chartData,
    xField: 'time',
    yField: 'value',
    seriesField: 'dimension',
    smooth: true,
    animation: {
      appear: {
        animation: 'path-in',
        duration: 1000,
      },
    },
    color: ['#38BDF8', '#E9A568', '#A78BFA'],
    legend: {
      position: 'top' as const,
    },
    yAxis: {
      min: 0,
      max: 1,
      label: {
        formatter: (v: string) => `${(parseFloat(v) * 100).toFixed(0)}%`,
      },
    },
    theme: {
      styleSheet: {
        backgroundColor: '#0A0D12',
      },
    },
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          padding: '20px',
          borderBottom: '1px solid #1E2636',
        }}
      >
        <Title level={5} style={{ margin: 0, color: '#E5E7EB' }}>
          当前元认知状态
        </Title>
        <Text style={{ fontSize: '12px', color: '#6B7280' }}>
          实时监测学习过程
        </Text>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '20px',
        }}
      >
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          {/* 当前状态 */}
          {currentState ? (
            <>
              <Card
                size="small"
                title={
                  <Space>
                    <span style={{ color: '#E5E7EB', fontSize: '14px' }}>
                      Planning
                    </span>
                    <Tag
                      color={getConfidenceColor(currentState.confidence)}
                      style={{ fontSize: '11px' }}
                    >
                      置信度: {(currentState.confidence * 100).toFixed(0)}%
                    </Tag>
                  </Space>
                }
                style={{
                  background: '#0F131C',
                  border: '1px solid #1E2636',
                  borderRadius: '12px',
                }}
              >
                <Progress
                  percent={currentState.planning * 100}
                  strokeColor={getStateColor(currentState.planning)}
                  trailColor="#1E2636"
                  format={(percent) => (
                    <span style={{ color: '#E5E7EB', fontSize: '13px' }}>
                      {percent?.toFixed(0)}%
                    </span>
                  )}
                />
              </Card>

              <Card
                size="small"
                title={
                  <Space>
                    <span style={{ color: '#E5E7EB', fontSize: '14px' }}>
                      Monitoring
                    </span>
                    <Tag
                      color={getConfidenceColor(currentState.confidence)}
                      style={{ fontSize: '11px' }}
                    >
                      置信度: {(currentState.confidence * 100).toFixed(0)}%
                    </Tag>
                  </Space>
                }
                style={{
                  background: '#0F131C',
                  border: '1px solid #1E2636',
                  borderRadius: '12px',
                }}
              >
                <Progress
                  percent={currentState.monitoring * 100}
                  strokeColor={getStateColor(currentState.monitoring)}
                  trailColor="#1E2636"
                  format={(percent) => (
                    <span style={{ color: '#E5E7EB', fontSize: '13px' }}>
                      {percent?.toFixed(0)}%
                    </span>
                  )}
                />
              </Card>

              <Card
                size="small"
                title={
                  <Space>
                    <span style={{ color: '#E5E7EB', fontSize: '14px' }}>
                      Evaluation
                    </span>
                    <Tag
                      color={getConfidenceColor(currentState.confidence)}
                      style={{ fontSize: '11px' }}
                    >
                      置信度: {(currentState.confidence * 100).toFixed(0)}%
                    </Tag>
                  </Space>
                }
                style={{
                  background: '#0F131C',
                  border: '1px solid #1E2636',
                  borderRadius: '12px',
                }}
              >
                <Progress
                  percent={currentState.evaluation * 100}
                  strokeColor={getStateColor(currentState.evaluation)}
                  trailColor="#1E2636"
                  format={(percent) => (
                    <span style={{ color: '#E5E7EB', fontSize: '13px' }}>
                      {percent?.toFixed(0)}%
                    </span>
                  )}
                />
              </Card>

              {/* 特征置信率 */}
              <Card
                size="small"
                style={{
                  background: '#0F131C',
                  border: '1px solid #1E2636',
                  borderRadius: '12px',
                }}
              >
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                    }}
                  >
                    <Text style={{ fontSize: '13px', color: '#9CA3AF' }}>
                      特征置信率
                    </Text>
                    <Text
                      style={{
                        fontSize: '15px',
                        color: '#38BDF8',
                        fontWeight: 600,
                      }}
                    >
                      {(currentState.confidence * 100).toFixed(0)} %
                    </Text>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                    }}
                  >
                    <Text style={{ fontSize: '13px', color: '#9CA3AF' }}>
                      计算版本
                    </Text>
                    <Text
                      style={{
                        fontSize: '13px',
                        color: '#6EE7B7',
                        fontFamily: 'monospace',
                      }}
                    >
                      v{currentState.version}
                    </Text>
                  </div>
                </Space>
              </Card>
            </>
          ) : (
            <div
              style={{
                textAlign: 'center',
                color: '#6B7280',
                fontSize: '13px',
                marginTop: '40px',
              }}
            >
              等待状态更新...
            </div>
          )}

          {/* 状态变化趋势 */}
          {stateHistory.length > 0 && (
            <Card
              size="small"
              title={
                <span style={{ color: '#E5E7EB', fontSize: '14px' }}>
                  状态变化趋势
                </span>
              }
              style={{
                background: '#0F131C',
                border: '1px solid #1E2636',
                borderRadius: '12px',
              }}
            >
              <Line {...chartConfig} />
            </Card>
          )}
        </Space>
      </div>
    </div>
  );
}
