/**
 * 清理AI响应中的思考标签
 * @param {string} aiResponse - AI的原始响应
 * @returns {string} 清理并格式化后的HTML
 */
// export function cleanAIResponse(aiResponse) {
//     try {
//         const cleanedResponse = aiResponse.replace(/<think>[\s\S]*?<\/think>/g, "");
//         return simpleMarkdownToHtml(cleanedResponse);
//     } catch (e) {
//         console.error('Error cleaning AI response:', e);
//         return aiResponse;
//     }
// }

/**
 * 将简单的Markdown文本转换为HTML
 * @param {string} markdown - 要转换的Markdown文本
 * @returns {string} 转换后的HTML
 */
export function simpleMarkdownToHtml(markdown) {
    // 处理代码块
    markdown = markdown.replace(
        /```([\s\S]*?)```/g,
        "<pre><code>$1</code></pre>"
    );

    // 处理行内代码
    markdown = markdown.replace(/`([^`]+)`/g, "<code>$1</code>");

    // 处理标题
    markdown = markdown.replace(/^###### (.*$)/gm, "<h6>$1</h6>");
    markdown = markdown.replace(/^##### (.*$)/gm, "<h5>$1</h5>");
    markdown = markdown.replace(/^#### (.*$)/gm, "<h4>$1</h4>");

    markdown = markdown.replace(/^### (.*$)/gm, "<h3>$1</h3>");
    markdown = markdown.replace(/^## (.*$)/gm, "<h2>$1</h2>");
    markdown = markdown.replace(/^# (.*$)/gm, "<h1>$1</h1>");

    // 处理 ** 加粗
    markdown = markdown.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    // 处理 * 斜体
    markdown = markdown.replace(/\*([^\*]+)\*/g, "<em>$1</em>");

    // 处理 [链接文本](URL)
    markdown = markdown.replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        '<a href="$2" target="_blank">$1</a>'
    );

    // 处理 - 列表项
    markdown = markdown.replace(/^- (.*$)/gm, "<li>$1</li>"); // 将 - 替换为 <li>
    markdown = markdown.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>"); // 将连续的 <li> 包裹在 <ul> 中

    // 处理 1. 有序列表
    markdown = markdown.replace(/^\d+\. (.*$)/gm, "<li>$1</li>");
    markdown = markdown.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ol>$1</ol>");

    // 处理 > 引用
    markdown = markdown.replace(/^> (.*$)/gm, "<blockquote>$1</blockquote>");

    // 处理换行符
    markdown = markdown.replace(/\n/g, "<br>");

    return markdown;
}