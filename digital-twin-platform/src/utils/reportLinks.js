/**
 * 诊断报告在各页面之间的关联：工作台、任务记录、独立报告页都按任务 ID 读同一份报告（GET /api/task/tasks/:id/report）。
 *
 *   独立报告页     /report/:taskId
 *   工作台定位部件  /?focus=部件  （工作台加载完三维模型后定位到该部件）
 */

export function reportPath(taskId) {
  return `/report/${encodeURIComponent(taskId)}`
}

/** 在新标签页打开独立报告页（工作台大屏、任务弹窗中使用，不打断当前页面） */
export function openReportInNewTab(router, taskId) {
  const { href } = router.resolve(reportPath(taskId))
  window.open(href, '_blank')
}

/** 跳到工作台并定位到部件 */
export function locateOnDashboard(router, component) {
  router.push({ path: '/', query: component ? { focus: component } : {} })
}

/** 报告中第一个需要定位的部件（异常优先；summarizeReport 已排好序） */
export function firstAlarmComponent(summary) {
  return (summary && summary.alarmComponents && summary.alarmComponents[0]) || null
}
