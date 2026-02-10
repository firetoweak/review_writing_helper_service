/**
 * static/js/markdown-processor.js
 * Markdown 处理器类
 * 提供Markdown格式检测、转换和处理功能
 */
class MarkdownProcessor {
    /**
     * 判断文本是否为Markdown格式
     * @param {string} text 要判断的文本
     * @returns {boolean} 是否为Markdown格式
     */
    static isMarkdown(text) {
        if (!text || typeof text !== 'string') return false;

        // Markdown常见语法模式
        const markdownPatterns = [
            /^#{1,6}\s/,                    // 标题 #, ##, ### 等
            /\*\*.+?\*\*/,                  // 粗体 **text**
            /\*.+?\*/,                      // 斜体 *text*
            /!\[.*?\]\(.*?\)/,              // 图片 ![alt](url)
            /\[.*?\]\(.*?\)/,               // 链接 [text](url)
            /^- .+/m,                       // 无序列表 - item
            /^\d+\. .+/m,                   // 有序列表 1. item
            /^> .+/m,                       // 引用 > text
            /```[\s\S]*?```/,               // 代码块 ```
            /`[^`]+`/,                      // 行内代码 `code`
            /\n---+\n/,                     // 分隔线 ---
            /\n\*\*\*+\n/,                  // 分隔线 ***
        ];

        // 检查是否包含HTML标签，如果包含则不认为是纯Markdown
        const hasHtmlTags = /<[a-z][\s\S]*>/i.test(text);

        // 如果包含HTML标签且不包含Markdown语法，则不是Markdown
        if (hasHtmlTags) {
            // 检查是否同时包含Markdown语法
            const hasMarkdownSyntax = markdownPatterns.some(pattern => pattern.test(text));
            return hasMarkdownSyntax;
        }

        // 检查是否包含Markdown语法
        return markdownPatterns.some(pattern => pattern.test(text));
    }

    /**
     * 将Markdown转换为HTML
     * @param {string} markdown Markdown文本
     * @returns {string} HTML文本
     */
    static markdownToHtml(markdown) {
        if (!markdown || typeof markdown !== 'string') return markdown || '';

        try {
            // 确保marked库已加载
            if (typeof marked === 'undefined') {
                console.warn('marked库未加载，将使用简易转换');
                return MarkdownProcessor.simpleMarkdownToHtml(markdown);
            }

            // 配置marked选项
            marked.setOptions({
                gfm: true,                    // 启用GitHub风格的Markdown
                breaks: true,                 // 将换行符转换为<br>
                smartypants: true,            // 使用智能引号等
                xhtml: false                  // 不使用XHTML自闭合标签
            });

            // 转换Markdown为HTML
            return marked.parse(markdown);
        } catch (error) {
            console.error('Markdown转换失败:', error);
            console.warn('降级解析路径触发');
            // 转换失败时返回原始文本
            return markdown;
        }
    }

    /**
     * 简易的Markdown转换（备选方案）
     * @param {string} markdown Markdown文本
     * @returns {string} HTML文本
     */
    static simpleMarkdownToHtml(markdown) {
        if (!markdown) return '';

        let html = markdown;

        // 标题转换
        html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');
        html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
        html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
        html = html.replace(/^#### (.*$)/gm, '<h4>$1</h4>');
        html = html.replace(/^##### (.*$)/gm, '<h5>$1</h5>');
        html = html.replace(/^###### (.*$)/gm, '<h6>$1</h6>');

        // 粗体
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__(.*?)__/g, '<strong>$1</strong>');

        // 斜体
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/_(.*?)_/g, '<em>$1</em>');

        // 无序列表
        html = html.replace(/^\s*[-*+]\s+(.*)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

        // 有序列表
        html = html.replace(/^\s*\d+\.\s+(.*)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ol>$&</ol>');

        // 链接
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

        // 图片
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1">');

        // 代码块
        html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');

        // 行内代码
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // 引用
        html = html.replace(/^>\s+(.*)$/gm, '<blockquote><p>$1</p></blockquote>');

        // 分隔线
        html = html.replace(/^\s*---\s*$/gm, '<hr>');
        html = html.replace(/^\s*\*\*\*\s*$/gm, '<hr>');

        // 段落（将连续的文本转换为段落）
        html = html.replace(/\n\n+/g, '</p><p>');
        html = '<p>' + html + '</p>';

        return html;
    }
}

// 如果是在浏览器环境中，将类添加到全局作用域
if (typeof window !== 'undefined') {
    window.MarkdownProcessor = MarkdownProcessor;
}
