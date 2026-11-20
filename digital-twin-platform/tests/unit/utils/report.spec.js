import { RESULT_TAG, resultLabel, summarizeReport } from '@/utils/report.js'

describe('Utils:report', () => {
  it('result labels include warning', () => {
    expect(resultLabel('warning')).toBe('预警')
    expect(resultLabel('abnormal')).toBe('异常')
    expect(resultLabel(undefined)).toBe('诊断中')
    expect(RESULT_TAG.warning).toBe('warning')
  })

  it('summarizeReport collects alarm components, abnormal first', () => {
    const report = {
      result: 'abnormal',
      summary: '异常：流量计读数偏离',
      findings: [
        { severity: 'info', component: '回油管路' },
        { severity: 'warning', component: '供油管路' },
        { severity: 'abnormal', component: '回油流量计2' },
        { severity: 'abnormal', component: null }
      ],
      product_info: { diag_date: '2026-11-11 17:00' }
    }
    const s = summarizeReport('t1', 'a.txt', report)
    expect(s.statusText).toBe('异常')
    expect(s.alarmComponents).toEqual(['回油流量计2', '供油管路'])
    expect(s.timestamp).toBe('2026-11-11 17:00')
    expect(s.loops).toEqual([])
  })
})
