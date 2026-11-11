/**
 * 把大模型回答里常见的 Markdown 转成 HTML。
 * 先整体做 HTML 转义，再处理 Markdown 语法，因此模型输出或用户输入里的 HTML 标签
 * 只会按文本显示，不会被执行（防 XSS）。
 */
function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function inline(text) {
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

export function renderMarkdown(source) {
  const blocks = escapeHtml(source || '').split(/```/)
  return blocks.map((block, i) => {
    if (i % 2 === 1) {
      // 代码块：去掉第一行的语言标记
      return `<pre><code>${block.replace(/^[\w-]*\n/, '')}</code></pre>`
    }
    const html = []
    let list = null
    const closeList = () => {
      if (list) html.push(`</${list}>`)
      list = null
    }
    for (const raw of block.split('\n')) {
      const line = raw.trimEnd()
      let m
      if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
        closeList()
        const level = Math.min(m[1].length + 2, 6) // 回答里的标题降级显示
        html.push(`<h${level}>${inline(m[2])}</h${level}>`)
      } else if ((m = line.match(/^\s*[-*]\s+(.*)$/))) {
        if (list !== 'ul') { closeList(); html.push('<ul>'); list = 'ul' }
        html.push(`<li>${inline(m[1])}</li>`)
      } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
        if (list !== 'ol') { closeList(); html.push('<ol>'); list = 'ol' }
        html.push(`<li>${inline(m[1])}</li>`)
      } else if (line.trim()) {
        closeList()
        html.push(`<p>${inline(line)}</p>`)
      } else {
        closeList()
      }
    }
    closeList()
    return html.join('')
  }).join('')
}
