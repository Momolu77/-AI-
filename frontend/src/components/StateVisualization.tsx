import { Card, Progress, Space, Tag, Statistic, Row, Col } from 'antd';
import { CheckCircleOutlined, QuestionCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { MetacogState } from '../types';

interface StateVisualizationProps {
  currentState: MetacogState | null;
  stateHistory: MetacogState[];
}

export default function StateVisualization({
  currentState,
  stateHistory,
}: StateVisualizationProps) {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'observed':
        return <CheckCircleOutlined style={{ color: '#6EE7B7' }} />;
      case 'unobserved':
        return <QuestionCircleOutlined style={{ color: '#9CA3AF' }} />;
      case 'insufficient':
        return <CloseCircleOutlined style={{ color: '#F87171' }} />;
      default:
        return null;
    }
  };

  const getProgressColor = (value: number | null) => {
    if (value === null) return '#4B5563';
    if (value >= 0.6) return '#6EE7B7';
    if (value >= 0.3) return '#E9A568';
    return '#F87171';
  };

  const getChartOption = () => {
    if (stateHistory.length === 0) return {};

    const times = stateHistory.map((_, idx) => `T${idx + 1}`);
    const planningData = stateHistory.map(s => s.planning);
    const monitoringData = stateHistory.map(s => s.monitoring);
    const evaluationData = stateHistory.map(s => s.evaluation);

    return {
      backgroundColor: 'transparent',
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: '12%',
        containLabel: true,
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1E2636',
        borderColor: '#38BDF8',
        textStyle: { color: '#E5E7EB' },
      },
      legend: {
        data: ['Planning', 'Monitoring', 'Evaluation'],
        textStyle: { color: '#9CA3AF' },
        top: 0,
      },
      xAxis: {
        type: 'category',
        data: times,
        axisLine: { lineStyle: { color: '#2A3441' } },
        axisLabel: { color: '#9CA3AF' },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 1,
        axisLine: { lineStyle: { color: '#2A3441' } },
        axisLabel: { color: '#9CA3AF' },
        splitLine: { lineStyle: { color: '#1E2636' } },
      },
      series: [
        {
          name: 'Planning',
          type: 'line',
          data: planningData,
          smooth: true,
          lineStyle: { color: '#38BDF8', width: 2 },
          itemStyle: { color: '#38BDF8' },
        },
        {
          name: 'Monitoring',
          type: 'line',
          data: monitoringData,
          smooth: true,
          lineStyle: { color: '#6EE7B7', width: 2 },
          itemStyle: { color: '#6EE7B7' },
        },
        {
          name: 'Evaluation',
          type: 'line',
          data: evaluationData,
          smooth: true,
          lineStyle: { color: '#E9A568', width: 2 },
          itemStyle: { color: '#E9A568' },
        },
      ],
    };
  };

  return (
    <div style={{
      height: '100%',
      overflowY: 'auto',
      padding: '20px',
      background: '#0A0D12',
    }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {/* Current State */}
        <Card
          title="当前元认知状态"
          size="small"
          style={{
            background: '#0F131C',
            border: '1px solid #1E2636',
            borderRadius: '12px',
          }}
          headStyle={{
            color: '#E5E7EB',
            borderBottom: '1px solid #1E2636',
          }}
          bodyStyle={{ padding: '16px' }}
        >
          {currentState ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              {/* Planning */}
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <span style={{ color: '#E5E7EB', fontWeight: 500 }}>Planning</span>
                  {getStatusIcon(currentState.status.planning)}
                  <Tag color="blue" style={{ marginLeft: 'auto' }}>
                    置信度: {(currentState.confidence.planning * 100).toFixed(0)}%
                  </Tag>
                </Space>
                <Progress
                  percent={
                    currentState.planning !== null
                      ? Math.round(currentState.planning * 100)
                      : 0
                  }
                  strokeColor={getProgressColor(currentState.planning)}
                  trailColor="#1E2636"
                  showInfo={currentState.planning !== null}
                  format={(percent) => `${percent}%`}
                />
              </div>

              {/* Monitoring */}
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <span style={{ color: '#E5E7EB', fontWeight: 500 }}>Monitoring</span>
                  {getStatusIcon(currentState.status.monitoring)}
                  <Tag color="green" style={{ marginLeft: 'auto' }}>
                    置信度: {(currentState.confidence.monitoring * 100).toFixed(0)}%
                  </Tag>
                </Space>
                <Progress
                  percent={
                    currentState.monitoring !== null
                      ? Math.round(currentState.monitoring * 100)
                      : 0
                  }
                  strokeColor={getProgressColor(currentState.monitoring)}
                  trailColor="#1E2636"
                  showInfo={currentState.monitoring !== null}
                />
              </div>

              {/* Evaluation */}
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <span style={{ color: '#E5E7EB', fontWeight: 500 }}>Evaluation</span>
                  {getStatusIcon(currentState.status.evaluation)}
                  <Tag color="orange" style={{ marginLeft: 'auto' }}>
                    置信度: {(currentState.confidence.evaluation * 100).toFixed(0)}%
                  </Tag>
                </Space>
                <Progress
                  percent={
                    currentState.evaluation !== null
                      ? Math.round(currentState.evaluation * 100)
                      : 0
                  }
                  strokeColor={getProgressColor(currentState.evaluation)}
                  trailColor="#1E2636"
                  showInfo={currentState.evaluation !== null}
                />
              </div>

              {/* Metadata */}
              <Row gutter={16} style={{ marginTop: 8 }}>
                <Col span={12}>
                  <Statistic
                    title={<span style={{ color: '#9CA3AF' }}>特征覆盖率</span>}
                    value={(currentState.feature_coverage * 100).toFixed(0)}
                    suffix="%"
                    valueStyle={{ color: '#38BDF8', fontSize: '16px' }}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title={<span style={{ color: '#9CA3AF' }}>计算版本</span>}
                    value={currentState.computation_version || 'N/A'}
                    valueStyle={{ color: '#6EE7B7', fontSize: '14px' }}
                  />
                </Col>
              </Row>
            </Space>
          ) : (
            <div style={{
              textAlign: 'center',
              padding: '40px 0',
              color: '#9CA3AF',
            }}>
              等待状态数据...
            </div>
          )}
        </Card>

        {/* History Chart */}
        <Card
          title="状态变化趋势"
          size="small"
          style={{
            background: '#0F131C',
            border: '1px solid #1E2636',
            borderRadius: '12px',
          }}
          headStyle={{
            color: '#E5E7EB',
            borderBottom: '1px solid #1E2636',
          }}
          bodyStyle={{ padding: '16px' }}
        >
          {stateHistory.length > 0 ? (
            <ReactECharts
              option={getChartOption()}
              style={{ height: '300px' }}
              opts={{ renderer: 'svg' }}
            />
          ) : (
            <div style={{
              textAlign: 'center',
              padding: '60px 0',
              color: '#9CA3AF',
            }}>
              暂无历史数据
            </div>
          )}
        </Card>
      </Space>
    </div>
  );
}
