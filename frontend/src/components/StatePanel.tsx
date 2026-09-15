import ReactECharts from 'echarts-for-react'
import { useSessionStore } from '@/store/sessionStore'

export default function StatePanel() {
  const state = useSessionStore(s => s.metacogState)
  const history = useSessionStore(s => s.stateHistory)

  const radarOption = {
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: '计划性\nPlanning', max: 1 },
        { name: '监控性\nMonitoring', max: 1 },
        { name: '评估性\nEvaluation', max: 1 },
      ],
      splitNumber: 4,
      axisName: { color: 'oklch(45% 0.02 264)', fontSize: 11 },
      splitLine: { lineStyle: { color: 'oklch(90% 0.01 264)' } },
      splitArea: { areaStyle: { color: ['oklch(98% 0.01 264)', 'oklch(95% 0.01 264)'] } },
    },
    series: [{
      type: 'radar',
      data: [{
        value: [state.planning, state.monitoring, state.evaluation],
        name: '当前状态',
        areaStyle: { color: 'oklch(60% 0.18 264 / 0.2)' },
        lineStyle: { color: 'oklch(55% 0.18 264)', width: 2 },
        itemStyle: { color: 'oklch(55% 0.18 264)' },
      }],
    }],
  }

  const timeLen = history.length
  const timeLabels = history.map((_, i) => i + 1)

  const lineOption = {
    backgroundColor: 'transparent',
    grid: { top: 12, right: 12, bottom: 24, left: 36 },
    xAxis: {
      type: 'category',
      data: timeLabels,
      axisLabel: { show: false },
      axisLine: { lineStyle: { color: 'oklch(88% 0.01 264)' } },
    },
    yAxis: {
      type: 'value',
      min: 0, max: 1,
      splitNumber: 3,
      axisLabel: { fontSize: 10, color: 'oklch(55% 0.02 264)' },
      splitLine: { lineStyle: { color: 'oklch(93% 0.01 264)' } },
    },
    legend: {
      bottom: 0,
      textStyle: { fontSize: 11, color: 'oklch(40% 0.02 264)' },
      itemWidth: 12, itemHeight: 3,
    },
    series: [
      {
        name: '计划', type: 'line', smooth: true, symbol: 'none',
        data: history.map(s => s.planning),
        lineStyle: { color: 'oklch(55% 0.18 264)', width: 1.5 },
      },
      {
        name: '监控', type: 'line', smooth: true, symbol: 'none',
        data: history.map(s => s.monitoring),
        lineStyle: { color: 'oklch(65% 0.18 150)', width: 1.5 },
      },
      {
        name: '评估', type: 'line', smooth: true, symbol: 'none',
        data: history.map(s => s.evaluation),
        lineStyle: { color: 'oklch(65% 0.18 30)', width: 1.5 },
      },
    ],
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 12,
      background: '#fff', borderRadius: 12,
      border: '1px solid oklch(92% 0.01 264)',
      padding: 16, overflow: 'hidden',
    }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: 'oklch(25% 0.04 264)' }}>
        元认知状态
      </span>

      <ReactECharts option={radarOption} style={{ height: 200 }} />

      {/* Score row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        {[
          { label: '计划性', value: state.planning, hue: 264 },
          { label: '监控性', value: state.monitoring, hue: 150 },
          { label: '评估性', value: state.evaluation, hue: 30 },
        ].map(({ label, value, hue }) => (
          <div key={label} style={{
            background: `oklch(97% 0.02 ${hue})`,
            borderRadius: 8, padding: '8px 10px', textAlign: 'center',
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: `oklch(45% 0.18 ${hue})` }}>
              {(value * 100).toFixed(0)}
            </div>
            <div style={{ fontSize: 11, color: `oklch(50% 0.08 ${hue})` }}>{label}</div>
          </div>
        ))}
      </div>

      {timeLen > 1 && (
        <>
          <span style={{ fontSize: 12, color: 'oklch(55% 0.02 264)', marginTop: 4 }}>
            状态历史趋势
          </span>
          <ReactECharts option={lineOption} style={{ height: 120 }} />
        </>
      )}
    </div>
  )
}
