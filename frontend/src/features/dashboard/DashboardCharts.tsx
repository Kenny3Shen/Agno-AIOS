import { useMemo } from 'react'
import ReactEChartsCore from 'echarts-for-react/esm/core'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { AxisPointerComponent, GridComponent, TooltipComponent } from 'echarts/components'
import type { EChartsOption } from 'echarts'
import { LabelLayout } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'
import { Card, theme } from 'antd'
import { useTranslation } from 'react-i18next'
import type { OverviewDimension } from './types'
import type { TimelineChartPoint } from './utils'

/**
 * Keep the ECharts runtime intentionally small. This module itself is lazy-loaded
 * by DashboardPage only after the overview contains visualizable data.
 */
echarts.use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, AxisPointerComponent, LabelLayout, CanvasRenderer])

interface DashboardChartsProps {
  timeline: TimelineChartPoint[]
  distribution: { dimension: string; items: OverviewDimension[] }
  formatDate: (value?: string | number | null) => string
}

export default function DashboardCharts({ timeline, distribution, formatDate }: DashboardChartsProps) {
  const { t, i18n } = useTranslation('dashboard')
  const { token } = theme.useToken()
  const numberFormat = useMemo(() => new Intl.NumberFormat(i18n.language), [i18n.language])
  const hasTimeline = timeline.some((item) => item.runs > 0)
  const hasDistribution = distribution.items.length > 0
  const common = useMemo(
    () => ({ textStyle: { color: token.colorTextSecondary }, backgroundColor: 'transparent' }),
    [token.colorTextSecondary]
  )

  const volumeOption = useMemo<EChartsOption>(
    () => ({
      ...common,
      animation: true,
      animationDuration: 260,
      animationDurationUpdate: 260,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      color: [token.colorPrimary, token.colorError, token.colorInfo, token.colorWarning],
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      grid: { top: 24, right: 112, bottom: 26, left: 40 },
      xAxis: { type: 'category', data: timeline.map((item) => item.time), axisLabel: { formatter: (value: string) => formatDate(value) } },
      yAxis: [
        { type: 'value', name: t('chartRuns'), minInterval: 1 },
        { type: 'value', name: t('chartErrorPct'), axisLabel: { formatter: '{value}%' } },
        {
          type: 'value',
          name: t('chartTokens'),
          position: 'right',
          offset: 56,
          axisLabel: { formatter: (value: number) => numberFormat.format(value) },
        },
      ],
      series: [
        {
          name: t('chartRuns'),
          type: 'line',
          data: timeline.map((item) => item.runs),
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { width: 2 },
        },
        {
          name: t('chartErrorRate'),
          type: 'line',
          yAxisIndex: 1,
          data: timeline.map((item) => item.errorRate),
          smooth: true,
          symbol: 'none',
        },
        {
          name: t('seriesInputTokens'),
          type: 'bar',
          yAxisIndex: 2,
          stack: 'tokens',
          data: timeline.map((item) => item.inputTokens),
          barMaxWidth: 22,
        },
        {
          name: t('seriesOutputTokens'),
          type: 'bar',
          yAxisIndex: 2,
          stack: 'tokens',
          data: timeline.map((item) => item.outputTokens),
          barMaxWidth: 22,
          itemStyle: { borderRadius: [3, 3, 0, 0] },
        },
      ],
    }),
    [common, formatDate, numberFormat, t, timeline, token.colorError, token.colorInfo, token.colorPrimary, token.colorWarning]
  )

  const latencyOption = useMemo<EChartsOption>(
    () => ({
      ...common,
      animation: true,
      animationDuration: 260,
      animationDurationUpdate: 260,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      color: [token.colorInfo, token.colorWarning],
      tooltip: { trigger: 'axis' },
      grid: { top: 24, right: 24, bottom: 26, left: 52 },
      xAxis: { type: 'category', data: timeline.map((item) => item.time), axisLabel: { formatter: (value: string) => formatDate(value) } },
      yAxis: { type: 'value', name: t('axisMs') },
      series: [
        { name: t('seriesP50'), type: 'line', data: timeline.map((item) => item.p50), smooth: true, symbol: 'none' },
        {
          name: t('seriesP95'),
          type: 'line',
          data: timeline.map((item) => item.p95),
          smooth: true,
          symbol: 'none',
          lineStyle: { width: 3 },
        },
      ],
    }),
    [common, formatDate, t, timeline, token.colorInfo, token.colorWarning]
  )

  const distributionOption = useMemo<EChartsOption>(
    () => ({
      ...common,
      animation: true,
      animationDuration: 260,
      animationDurationUpdate: 260,
      animationEasing: 'cubicOut',
      animationEasingUpdate: 'cubicOut',
      color: [token.colorPrimary, token.colorSuccess, token.colorWarning, token.colorError, token.colorInfo],
      tooltip: { trigger: 'item' },
      series: [
        {
          name: distribution.dimension,
          type: 'pie',
          radius: ['46%', '76%'],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: token.colorBgContainer, borderWidth: 2 },
          label: { formatter: '{b}  {d}%' },
          data: distribution.items.map((item) => ({ name: item.name, value: item.value })),
        },
      ],
    }),
    [
      common,
      distribution.dimension,
      distribution.items,
      token.colorBgContainer,
      token.colorError,
      token.colorInfo,
      token.colorPrimary,
      token.colorSuccess,
      token.colorWarning,
    ]
  )

  return (
    <>
      <section className="dashboard-grid dashboard-primary-grid dashboard-motion-group" aria-label={t('observability')}>
        {hasTimeline && (
          <Card className="workbench-card dashboard-chart-card dashboard-motion-item" title={t('timelineTitle')}>
            <figure className="dashboard-chart-figure">
              <figcaption className="dashboard-chart-caption">{t('timelineTitle')}</figcaption>
              <ReactEChartsCore echarts={echarts} option={volumeOption} style={{ height: 300 }} opts={{ renderer: 'canvas' }} />
            </figure>
          </Card>
        )}
        {hasDistribution && (
          <Card
            className="workbench-card dashboard-chart-card dashboard-motion-item"
            title={t('distributionTitle', { dimension: distribution.dimension })}
          >
            <figure className="dashboard-chart-figure">
              <figcaption className="dashboard-chart-caption">{t('distributionTitle', { dimension: distribution.dimension })}</figcaption>
              <ReactEChartsCore echarts={echarts} option={distributionOption} style={{ height: 300 }} opts={{ renderer: 'canvas' }} />
            </figure>
          </Card>
        )}
      </section>
      {hasTimeline && (
        <section className="dashboard-grid dashboard-secondary-grid dashboard-motion-group" aria-label={t('latencyTrend')}>
          <Card className="workbench-card dashboard-chart-card dashboard-motion-item" title={t('latencyTrend')}>
            <figure className="dashboard-chart-figure">
              <figcaption className="dashboard-chart-caption">{t('latencyTrend')}</figcaption>
              <ReactEChartsCore echarts={echarts} option={latencyOption} style={{ height: 260 }} opts={{ renderer: 'canvas' }} />
            </figure>
          </Card>
        </section>
      )}
    </>
  )
}
