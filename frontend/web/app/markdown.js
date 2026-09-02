/**
 * OfferCabin Markdown 渲染器
 * 从 agent.html 提取的轻量 MD 渲染（代码块优先、HTML 转义、标题/列表/表格/段落）
 */
(function (global) {
    'use strict';

    /**
     * 渲染 Markdown 文本为安全 HTML
     */
    function render(text) {
        if (!text) return '';
        let md = String(text);

        // 1. 提取代码块（防止后续正则破坏）
        const codeBlocks = [];
        md = md.replace(/```(\w*)\n?([\s\S]*?)```/g, function (_, lang, code) {
            const idx = codeBlocks.length;
            codeBlocks.push({ lang: lang || '', code: code.replace(/\n$/, '') });
            return '\u0000CODE' + idx + '\u0000';
        });

        // 2. HTML 转义
        md = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        // 3. 行内代码
        md = md.replace(/`([^`\n]+)`/g, '<code class="md-code-inline">$1</code>');

        // 4. 标题
        md = md.replace(/^####\s+(.+)$/gm, '<h4 class="md-h4">$1</h4>');
        md = md.replace(/^###\s+(.+)$/gm, '<h3 class="md-h3">$1</h3>');
        md = md.replace(/^##\s+(.+)$/gm, '<h2 class="md-h2">$1</h2>');
        md = md.replace(/^#\s+(.+)$/gm, '<h1 class="md-h1">$1</h1>');

        // 5. 粗体 / 斜体
        md = md.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        md = md.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

        // 6. 分隔线
        md = md.replace(/^---+$/gm, '<hr class="md-hr">');

        // 7. 表格
        md = md.replace(/^\|(.+)\|\n\|([-:\s|]+)\|\n((?:\|.+\|\n?)*)/gm, function (_, header, _sep, body) {
            const heads = header.split('|').map(s => s.trim()).filter(Boolean);
            const rows = body.trim().split('\n').map(row =>
                row.split('|').map(s => s.trim()).filter(Boolean)
            );
            let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
            heads.forEach(h => { html += '<th>' + h + '</th>'; });
            html += '</tr></thead><tbody>';
            rows.forEach(row => {
                html += '<tr>';
                for (let i = 0; i < heads.length; i++) {
                    html += '<td>' + (row[i] || '') + '</td>';
                }
                html += '</tr>';
            });
            html += '</tbody></table></div>';
            return html;
        });

        // 8. 无序列表
        md = md.replace(/^(\s*)[-*]\s+(.+)$/gm, '$1<li>$2</li>');
        md = md.replace(/(<li>.*<\/li>\n?)+/g, function (m) {
            return '<ul class="md-ul">' + m.replace(/\n/g, '') + '</ul>';
        });

        // 9. 有序列表
        md = md.replace(/^(\s*)\d+\.\s+(.+)$/gm, '$1<li>$2</li>');
        md = md.replace(/(<li>.*<\/li>\n?)+(?!<\/ul>)/g, function (m) {
            if (m.includes('<ul')) return m;
            return '<ol class="md-ol">' + m.replace(/\n/g, '') + '</ol>';
        });

        // 10. 段落（连续非空行非标签内容）
        md = md.replace(/^(?!<[a-z/])(.+)$/gm, function (m) {
            if (m.trim() === '' || m.startsWith('\u0000CODE')) return m;
            return '<p class="md-p">' + m + '</p>';
        });

        // 11. 还原代码块
        md = md.replace(/\u0000CODE(\d+)\u0000/g, function (_, idx) {
            const block = codeBlocks[parseInt(idx)];
            const langLabel = block.lang ? '<span class="md-code-lang">' + block.lang + '</span>' : '';
            const code = block.code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return '<div class="md-code-block"><div class="md-code-head">' + langLabel +
                '<button class="md-copy-btn" type="button" data-code="' + code.replace(/"/g, '&quot;') + '">复制</button></div>' +
                '<pre><code>' + code + '</code></pre></div>';
        });

        return md;
    }

    global.OfferCabinMarkdown = { render };
})(window);
