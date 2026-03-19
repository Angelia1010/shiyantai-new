import defaultSettings from '@/settings'

const title = defaultSettings.title || '数字孪生平台'

export default function getPageTitle(pageTitle) {
  if (pageTitle) {
    return `${pageTitle} - ${title}`
  }
  return `${title}`
}
