/**
 * 面试复盘视图 — LLM 辅助分析 + 日志条目
 * 双 Tab：面试复盘（新建复盘 + 历史复盘）/ 周报（生成与保存）
 * 当后端日志 API 尚未实现时优雅降级，给出友好提示
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const Motion = global.OfferClawMotion;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const CSS_ID = 'interview-styles';

    const ENTRY_TYPE = 'interview_review';
    const WEEKLY_TYPE = 'weekly_summary';

    // ============ 状态 ============

    const state = {
        tab: 'review',                 // 'review' | 'weekly'
        form: { company: '', position: '', application_id: '', notes: '' },
        applications: [],              // 已有投递记录（用于 datalist / 下拉）
        appsLoaded: false,
        analyzing: false,              // AI 复盘进行中
        analysis: null,               // LLM 分析结果
        analysisError: null,
        savingReview: false,
        // 历史复盘
        pastReviews: [],
        loadingReviews: false,
        reviewsError: null,
        apiAvailable: true,            // 日志 API 是否可用（首次 GET 失败后置 false）
        expandedId: null,              // 展开的历史复盘 id
        deletingId: null,
        // 周报
        weekly: null,                  // { summary, highlights, action_items, generated_at? }
        loadingWeekly: false,
        weeklyError: null,
        savingWeekly: false,
    };

    let root = null;
    let timers = [];

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.interview-view { padding-bottom: 4rem; }

/* --- Tab 面板 --- */
.tab-panels { margin-top: 1.2rem; }
.tab-panel { animation: ivPanelIn 0.3s var(--ease-out); }
@keyframes ivPanelIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}

/* --- 复盘表单 --- */
.review-form-card { margin-bottom: 1.2rem; }
.review-form-card .card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 1rem;
}
.review-form-card .card-title {
    font-family: var(--font-serif);
    font-size: 1rem; font-weight: 700; color: var(--ink);
    display: flex; align-items: center; gap: 0.5rem;
}
.review-form-card .card-title::before {
    content: '✎'; color: var(--olive); font-size: 1.1rem;
}
.iv-notes {
    width: 100%;
    min-height: 160px;
    padding: 0.7rem 0.9rem;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.9rem;
    font-family: inherit;
    line-height: 1.6;
    resize: vertical;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.iv-notes:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: var(--card);
}
.iv-form-actions {
    display: flex; gap: 0.6rem; align-items: center;
    margin-top: 1rem; flex-wrap: wrap;
}
.iv-form-actions .btn-ai {
    background: linear-gradient(135deg, var(--olive), var(--olive-dark));
    color: var(--paper-light);
    font-weight: 600;
}
.iv-form-actions .btn-ai:hover:not(:disabled) {
    box-shadow: 0 4px 14px rgba(76, 84, 31, 0.3);
}
.iv-form-hint {
    font-size: 0.76rem; color: var(--ink-faint);
    margin-left: auto;
}

/* --- 分析结果卡 --- */
.analysis-card { margin-bottom: 1.4rem; }
.analysis-card .card-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 1rem; padding-bottom: 0.8rem;
    border-bottom: 1px dashed var(--line-soft);
}
.analysis-card .card-title {
    font-family: var(--font-serif);
    font-size: 1rem; font-weight: 700; color: var(--ink);
    display: flex; align-items: center; gap: 0.5rem;
}
.analysis-card .card-title::before {
    content: '✨'; font-size: 1rem;
}
.analysis-actions { display: flex; gap: 0.5rem; }

/* --- 评分卡 --- */
.score-card {
    display: flex; gap: 1.6rem; align-items: center;
    padding: 1.2rem; margin-bottom: 1.2rem;
    background: var(--paper-light);
    border: 1px solid var(--line-soft);
    border-radius: 12px;
    flex-wrap: wrap;
}
.score-circle {
    width: 110px; height: 110px;
    border-radius: 50%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    flex-shrink: 0;
    border: 4px solid;
    background: var(--card);
    transition: transform 0.4s var(--ease-out);
}
.score-circle:hover { transform: scale(1.03); }
.score-circle.score-good { border-color: var(--success); color: var(--success); }
.score-circle.score-mid  { border-color: var(--warn); color: var(--warn); }
.score-circle.score-bad  { border-color: var(--danger); color: var(--danger); }
.score-value {
    font-family: var(--font-serif);
    font-size: 2.2rem; font-weight: 800;
    line-height: 1;
}
.score-label {
    font-size: 0.72rem; color: var(--ink-soft);
    margin-top: 0.25rem; letter-spacing: 0.05em;
}
.score-breakdown {
    flex: 1; min-width: 240px;
    display: flex; flex-direction: column; gap: 0.6rem;
}
.score-item { display: flex; align-items: center; gap: 0.7rem; }
.score-item-label {
    font-size: 0.8rem; color: var(--ink-soft);
    min-width: 84px; flex-shrink: 0;
}
.score-bar {
    flex: 1; height: 8px;
    background: var(--paper-deep);
    border-radius: 5px; overflow: hidden;
}
.score-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--olive), var(--olive-dark));
    border-radius: 5px;
    transition: width 0.8s var(--ease-out);
}
.score-item-pct {
    font-family: var(--font-mono);
    font-size: 0.76rem; color: var(--ink-soft);
    min-width: 32px; text-align: right;
}

/* --- 分析区段 --- */
.iv-section { margin-bottom: 1.1rem; }
.iv-section:last-child { margin-bottom: 0; }
.iv-section-title {
    font-family: var(--font-serif);
    font-size: 0.92rem; font-weight: 700;
    color: var(--ink);
    margin-bottom: 0.5rem;
    display: flex; align-items: center; gap: 0.4rem;
}
.iv-section-title .iv-section-icon {
    width: 22px; height: 22px;
    border-radius: 6px;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700;
    background: var(--olive-soft); color: var(--olive-dark);
}
.iv-section-title.strengths .iv-section-icon { background: rgba(40, 167, 69, 0.12); color: var(--success); }
.iv-section-title.weaknesses .iv-section-icon { background: var(--terra-soft); color: var(--terra-deep); }
.iv-section-title.suggestions .iv-section-icon { background: var(--olive-soft); color: var(--olive-dark); }
.iv-summary-text {
    font-size: 0.88rem; line-height: 1.7;
    color: var(--ink-soft);
    padding: 0.7rem 0.9rem;
    background: var(--paper-light);
    border-left: 3px solid var(--olive);
    border-radius: 0 6px 6px 0;
}
.iv-bullet-list {
    list-style: none; padding: 0; margin: 0;
    display: flex; flex-direction: column; gap: 0.4rem;
}
.iv-bullet-list li {
    font-size: 0.86rem; color: var(--ink-soft);
    padding-left: 1.1rem; position: relative;
    line-height: 1.6;
}
.iv-bullet-list li::before {
    content: ''; position: absolute;
    left: 0.2rem; top: 0.55em;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--olive);
}
.iv-bullet-list.weaknesses li::before { background: var(--terra); }
.iv-bullet-list.suggestions li::before { background: var(--olive-dark); }

/* --- 问题分析表 --- */
.iv-questions-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    background: var(--card);
    border: 1px solid var(--line-soft);
    border-radius: 8px;
    overflow: hidden;
}
.iv-questions-table th {
    text-align: left;
    padding: 0.6rem 0.8rem;
    background: var(--paper-light);
    color: var(--ink-soft);
    font-weight: 600;
    font-size: 0.78rem;
    border-bottom: 1px solid var(--line-soft);
}
.iv-questions-table td {
    padding: 0.6rem 0.8rem;
    color: var(--ink);
    border-bottom: 1px solid var(--line-soft);
    vertical-align: top;
}
.iv-questions-table tr:last-child td { border-bottom: none; }
.iv-questions-table .q-quality {
    display: inline-block;
    font-size: 0.72rem; font-weight: 600;
    padding: 0.15rem 0.55rem;
    border-radius: 10px;
    white-space: nowrap;
}
.q-quality.good { background: color-mix(in srgb, var(--success) 13%, var(--card)); color: var(--success); }
.q-quality.mid  { background: color-mix(in srgb, var(--warn) 13%, var(--card)); color: var(--warn); }
.q-quality.bad  { background: var(--terra-soft); color: var(--terra-deep); }

/* --- 历史复盘列表 --- */
.past-reviews { margin-top: 1.6rem; }
.past-reviews-head {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 0.9rem;
}
.past-reviews-title {
    font-family: var(--font-serif);
    font-size: 1rem; font-weight: 700; color: var(--ink);
}
.past-reviews-count {
    font-size: 0.78rem; color: var(--ink-faint);
    font-family: var(--font-mono);
}
.review-list {
    display: flex; flex-direction: column; gap: 0.7rem;
}
.review-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
    transition: box-shadow 0.2s var(--ease), border-color 0.2s var(--ease);
}
.review-card:hover { box-shadow: var(--shadow-sm); border-color: var(--olive); }
.review-card.expanded { border-color: var(--olive); }
.review-card-head {
    display: flex; align-items: center; gap: 0.8rem;
    padding: 0.9rem 1.1rem;
    cursor: pointer;
    transition: background 0.15s var(--ease);
}
.review-card-head:hover { background: var(--paper-light); }
.review-card-main { flex: 1; min-width: 0; }
.review-card-row1 {
    display: flex; align-items: center; gap: 0.6rem;
    margin-bottom: 0.2rem; flex-wrap: wrap;
}
.review-company {
    font-family: var(--font-serif);
    font-size: 0.94rem; font-weight: 700; color: var(--ink);
}
.review-position {
    font-size: 0.82rem; color: var(--ink-soft);
}
.review-date {
    font-size: 0.74rem; color: var(--ink-faint);
    font-family: var(--font-mono);
}
.review-score-badge {
    font-family: var(--font-mono);
    font-size: 0.78rem; font-weight: 700;
    padding: 0.2rem 0.55rem;
    border-radius: 10px;
    flex-shrink: 0;
}
.review-score-badge.good { background: color-mix(in srgb, var(--success) 13%, var(--card)); color: var(--success); }
.review-score-badge.mid  { background: color-mix(in srgb, var(--warn) 13%, var(--card)); color: var(--warn); }
.review-score-badge.bad  { background: var(--terra-soft); color: var(--terra-deep); }
.review-score-badge.none { background: var(--paper-deep); color: var(--ink-faint); }
.review-preview {
    font-size: 0.82rem; color: var(--ink-soft);
    line-height: 1.5;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
}
.review-card-chevron {
    color: var(--ink-faint);
    font-size: 0.9rem;
    transition: transform 0.2s var(--ease);
    flex-shrink: 0;
}
.review-card.expanded .review-card-chevron { transform: rotate(90deg); }
.review-card-body {
    padding: 0 1.1rem 1rem;
    border-top: 1px dashed var(--line-soft);
    animation: ivPanelIn 0.2s var(--ease-out);
}
.review-card-body .iv-section { margin-top: 0.9rem; }
.review-card-notes {
    margin-top: 0.9rem;
    padding: 0.7rem 0.9rem;
    background: var(--paper-light);
    border-radius: 6px;
    font-size: 0.82rem;
    color: var(--ink-soft);
    line-height: 1.6;
    white-space: pre-wrap;
}
.review-card-actions {
    display: flex; gap: 0.5rem;
    margin-top: 0.9rem;
    padding-top: 0.7rem;
    border-top: 1px dashed var(--line-soft);
}

/* --- 周报 --- */
.weekly-panel { display: flex; flex-direction: column; gap: 1.2rem; }
.weekly-generate-card {
    display: flex; align-items: center; gap: 1rem;
    padding: 1.2rem 1.4rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    flex-wrap: wrap;
}
.weekly-generate-info { flex: 1; min-width: 200px; }
.weekly-generate-title {
    font-family: var(--font-serif);
    font-size: 0.96rem; font-weight: 700; color: var(--ink);
    margin-bottom: 0.25rem;
}
.weekly-generate-desc {
    font-size: 0.8rem; color: var(--ink-soft);
    line-height: 1.5;
}
.weekly-result-card { padding: 1.4rem; }
.weekly-meta {
    font-size: 0.76rem; color: var(--ink-faint);
    font-family: var(--font-mono);
    margin-bottom: 0.9rem;
}
.weekly-highlights {
    list-style: none; padding: 0; margin: 0;
    display: flex; flex-direction: column; gap: 0.45rem;
}
.weekly-highlights li {
    font-size: 0.86rem; color: var(--ink-soft);
    padding-left: 1.3rem; position: relative;
    line-height: 1.6;
}
.weekly-highlights li::before {
    content: '★'; position: absolute;
    left: 0; top: 0;
    color: var(--olive); font-size: 0.85rem;
}
.weekly-actions-list {
    list-style: none; padding: 0; margin: 0;
    display: flex; flex-direction: column; gap: 0.5rem;
}
.weekly-action-item {
    display: flex; align-items: flex-start; gap: 0.6rem;
    font-size: 0.86rem; color: var(--ink-soft);
    line-height: 1.55;
}
.weekly-action-item input[type="checkbox"] {
    margin-top: 0.2rem;
    accent-color: var(--olive);
    flex-shrink: 0;
}
.weekly-action-item.checked {
    color: var(--ink-faint);
    text-decoration: line-through;
}
.weekly-actions-footer {
    display: flex; gap: 0.5rem;
    margin-top: 1.2rem; padding-top: 1rem;
    border-top: 1px dashed var(--line-soft);
}

/* --- API 不可用提示 --- */
.api-unavailable-card {
    display: flex; flex-direction: column;
    align-items: center; gap: 0.6rem;
    padding: 2.2rem 1.5rem;
    text-align: center;
}
.api-unavailable-icon {
    font-size: 2.2rem;
    line-height: 1;
}
.api-unavailable-title {
    font-family: var(--font-serif);
    font-size: 1.05rem; font-weight: 700; color: var(--ink);
}
.api-unavailable-desc {
    font-size: 0.84rem; color: var(--ink-soft);
    line-height: 1.6; max-width: 420px;
}
.api-unavailable-tag {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    padding: 0.2rem 0.6rem;
    background: var(--paper-deep);
    color: var(--ink-faint);
    border-radius: 10px;
    margin-top: 0.3rem;
}

/* --- 分析中加载态 --- */
.analyzing-state {
    display: flex; flex-direction: column;
    align-items: center; gap: 0.8rem;
    padding: 2.2rem 1rem;
    color: var(--ink-soft);
    font-size: 0.88rem;
}
.analyzing-state .spinner {
    width: 32px; height: 32px;
    border-width: 3px;
}
.analyzing-state .analyzing-tip {
    font-size: 0.78rem; color: var(--ink-faint);
}

@media (max-width: 700px) {
    .score-card { flex-direction: column; align-items: stretch; }
    .score-circle { align-self: center; }
    .review-card-head { flex-wrap: wrap; }
    .weekly-generate-card { flex-direction: column; align-items: stretch; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function clearTimers() {
        timers.forEach(t => clearTimeout(t));
        timers = [];
    }

    function formatDate(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
    }

    function formatDateTime(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        return d.toLocaleString('zh-CN', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit',
        });
    }

    function formatRelative(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        const diff = Date.now() - d.getTime();
        if (diff < 0) return formatDate(ts);
        if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前';
        if (diff < 604800000) return Math.floor(diff / 86400000) + ' 天前';
        return formatDate(ts);
    }

    /** 根据分数返回颜色档位 */
    function scoreTier(score) {
        const n = Number(score);
        if (!isFinite(n)) return 'none';
        if (n > 70) return 'good';
        if (n >= 50) return 'mid';
        return 'bad';
    }

    function qualityClass(q) {
        const s = String(q || '').toLowerCase();
        if (['good', '优秀', '好', 'strong', 'a', '优'].includes(s)) return 'good';
        if (['bad', '差', '弱', 'weak', 'c', '差评'].includes(s)) return 'bad';
        return 'mid';
    }

    function qualityLabel(q) {
        const s = String(q || '').toLowerCase();
        if (['good', '优秀', '好', 'strong', 'a', '优'].includes(s)) return '优秀';
        if (['bad', '差', '弱', 'weak', 'c', '差评'].includes(s)) return '待改进';
        if (s) return String(q);
        return '一般';
    }

    /** 从 questions 数组提取每行 {question, answer, quality} */
    function normalizeQuestions(qs) {
        if (!qs) return [];
        if (typeof qs === 'string') return [{ question: qs, answer: '', quality: '' }];
        if (!Array.isArray(qs)) return [];
        return qs.map(q => {
            if (typeof q === 'string') return { question: q, answer: '', quality: '' };
            if (!q || typeof q !== 'object') return null;
            return {
                question: q.question || q.q || q.title || '',
                answer: q.answer || q.your_answer || q.response || q.answer_summary || '',
                quality: q.quality || q.quality_score || q.score || q.rating || '',
            };
        }).filter(Boolean);
    }

    /** 规范化 LLM 分析结果（兼容字段缺失） */
    function normalizeAnalysis(data) {
        if (!data || typeof data !== 'object') return null;
        const score = data.score != null ? Number(data.score) : null;
        return {
            score: isFinite(score) ? score : null,
            summary: data.summary || data.overall_summary || '',
            strengths: Array.isArray(data.strengths) ? data.strengths :
                (typeof data.strengths === 'string' ? data.strengths : ''),
            weaknesses: Array.isArray(data.weaknesses) ? data.weaknesses :
                (typeof data.weaknesses === 'string' ? data.weaknesses : ''),
            suggestions: Array.isArray(data.suggestions) ? data.suggestions :
                (typeof data.suggestions === 'string' ? data.suggestions : ''),
            questions: normalizeQuestions(data.questions),
            breakdown: Array.isArray(data.breakdown) ? data.breakdown : null,
        };
    }

    function textToList(text) {
        if (!text) return [];
        return String(text).split('\n').map(s => s.trim()).filter(Boolean);
    }

    /** 规范化日志条目（兼容字段命名差异） */
    function normalizeEntry(e) {
        if (!e || typeof e !== 'object') return null;
        let meta = e.metadata || e.meta || {};
        if (typeof meta === 'string') {
            try { meta = JSON.parse(meta) || {}; } catch (_) { meta = {}; }
        }
        return {
            id: e.id,
            user_id: e.user_id,
            entry_type: e.entry_type || ENTRY_TYPE,
            application_id: e.application_id || null,
            title: e.title || '',
            content: e.content || '',
            metadata: meta || {},
            mood_score: e.mood_score,
            created_at: e.created_at,
            updated_at: e.updated_at,
        };
    }

    /** 判断错误是否表示 API 不可用（404 / 路由未实现） */
    function isApiMissingError(e) {
        if (!e) return false;
        if (e.status === 404 || e.status === 405) return true;
        const msg = String(e.message || '').toLowerCase();
        if (msg.includes('not found') || msg.includes('404')) return true;
        return false;
    }

    // ============ 渲染：骨架 ============

    function renderShell() {
        return `
        <div class="view-container interview-view">
            <div class="view-header">
                <div class="header-eyebrow">INTERVIEW</div>
                <h1>面试复盘</h1>
                <p>AI 辅助分析面试表现，持续改进求职策略</p>
            </div>
            <div class="tabs" id="iv-tabs">
                <button class="tab ${state.tab === 'review' ? 'active' : ''}" data-tab="review">面试复盘</button>
                <button class="tab ${state.tab === 'weekly' ? 'active' : ''}" data-tab="weekly">周报</button>
            </div>
            <div class="tab-panels">
                <div class="tab-panel" id="panel-review" ${state.tab === 'review' ? '' : 'hidden'}>
                    <div class="card review-form-card" id="review-form-card"></div>
                    <div id="analysis-container"></div>
                    <div class="past-reviews" id="past-reviews"></div>
                </div>
                <div class="tab-panel" id="panel-weekly" ${state.tab === 'weekly' ? '' : 'hidden'}></div>
            </div>
        </div>`;
    }

    // ============ 渲染：复盘表单 ============

    function renderReviewForm() {
        const f = state.form;
        const companyDatalist = state.applications
            .map(a => a.company).filter(Boolean)
            .filter((v, i, arr) => arr.indexOf(v) === i)
            .map(c => `<option value="${esc(c)}">`).join('');

        const appOptions = ['<option value="">不关联投递</option>']
            .concat(state.applications.map(a => {
                const label = `${a.company || '未知公司'} · ${a.position || '未知职位'}`;
                return `<option value="${esc(a.id)}"${a.id === f.application_id ? ' selected' : ''}>${esc(label)}</option>`;
            }))
            .join('');

        return `
        <div class="card-header">
            <span class="card-title">新建面试复盘</span>
        </div>
        <div class="form-grid">
            <div class="form-field">
                <label>公司</label>
                <input type="text" id="iv-company" list="iv-company-list"
                    value="${esc(f.company)}" placeholder="如 字节跳动" autocomplete="off">
                <datalist id="iv-company-list">${companyDatalist}</datalist>
            </div>
            <div class="form-field">
                <label>职位</label>
                <input type="text" id="iv-position"
                    value="${esc(f.position)}" placeholder="如 后端工程师" autocomplete="off">
            </div>
            <div class="form-field full">
                <label>关联投递（可选）</label>
                <select id="iv-application">
                    ${appOptions}
                </select>
            </div>
            <div class="form-field full">
                <label>面试笔记</label>
                <textarea class="iv-notes" id="iv-notes" rows="7"
                    placeholder="记录面试中被问到的问题、你的回答、感受...&#10;&#10;例如：&#10;1. 自我介绍&#10;2. 项目深挖：问了 XX 系统的架构设计&#10;3. 算法题：反转链表，时间复杂度？&#10;4. 反问环节">${esc(f.notes)}</textarea>
            </div>
        </div>
        <div class="iv-form-actions">
            <button class="btn btn-ai" id="iv-analyze-btn" ${state.analyzing ? 'disabled' : ''}>
                ${state.analyzing ? '<span class="spinner" style="width:14px;height:14px;border-width:2px;margin-right:0.4rem;vertical-align:-2px"></span>AI 分析中...' : '✨ AI 复盘'}
            </button>
            <button class="btn btn-ghost btn-sm" id="iv-clear-btn">清空</button>
            <span class="iv-form-hint">AI 将分析你的回答并给出改进建议</span>
        </div>`;
    }

    // ============ 渲染：分析结果 ============

    function renderAnalysisContainer() {
        const container = root.querySelector('#analysis-container');
        if (!container) return;

        if (state.analyzing) {
            container.innerHTML = `
            <div class="card analysis-card">
                <div class="analyzing-state">
                    <div class="spinner"></div>
                    <span>AI 正在分析你的面试表现...</span>
                    <span class="analyzing-tip">通常需要 10-30 秒，请稍候</span>
                </div>
            </div>`;
            return;
        }

        if (state.analysisError && !state.analysis) {
            container.innerHTML = `
            <div class="card analysis-card">
                <div class="empty-card">
                    <span class="empty-emoji">⚠️</span>
                    <h3>AI 分析失败</h3>
                    <p>${esc(state.analysisError)}</p>
                    <p style="font-size:0.8rem;color:var(--ink-faint);margin-top:0.5rem">你可以修改笔记后重试，或直接保存为日志</p>
                </div>
            </div>`;
            return;
        }

        if (!state.analysis) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML = `<div class="card analysis-card">${renderAnalysisBody(state.analysis)}</div>`;
    }

    function renderAnalysisBody(a) {
        let html = '';

        // 头部
        html += `
        <div class="card-header">
            <span class="card-title">AI 复盘结果</span>
            <div class="analysis-actions">
                <button class="btn btn-ghost btn-sm" id="iv-reanalyze-btn">重新分析</button>
                <button class="btn btn-primary btn-sm" id="iv-save-review-btn" ${state.savingReview ? 'disabled' : ''}>
                    ${state.savingReview ? '保存中...' : '保存为日志'}
                </button>
            </div>
        </div>`;

        // 评分卡
        if (a.score != null) {
            const tier = scoreTier(a.score);
            html += `
            <div class="score-card">
                <div class="score-circle score-${tier}">
                    <span class="score-value">${esc(String(Math.round(a.score)))}</span>
                    <span class="score-label">综合评分</span>
                </div>
                ${a.breakdown ? renderScoreBreakdown(a.breakdown) : ''}
            </div>`;
        }

        // 总结
        if (a.summary) {
            html += `
            <div class="iv-section">
                <div class="iv-section-title"><span class="iv-section-icon">摘</span>总结</div>
                <div class="iv-summary-text">${esc(a.summary)}</div>
            </div>`;
        }

        // 优势
        if (a.strengths) {
            const list = Array.isArray(a.strengths) ? a.strengths : textToList(a.strengths);
            if (list.length) {
                html += `
                <div class="iv-section">
                    <div class="iv-section-title strengths"><span class="iv-section-icon">优</span>表现亮点</div>
                    <ul class="iv-bullet-list">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
                </div>`;
            }
        }

        // 不足
        if (a.weaknesses) {
            const list = Array.isArray(a.weaknesses) ? a.weaknesses : textToList(a.weaknesses);
            if (list.length) {
                html += `
                <div class="iv-section">
                    <div class="iv-section-title weaknesses"><span class="iv-section-icon">缺</span>待改进</div>
                    <ul class="iv-bullet-list weaknesses">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
                </div>`;
            }
        }

        // 建议
        if (a.suggestions) {
            const list = Array.isArray(a.suggestions) ? a.suggestions : textToList(a.suggestions);
            if (list.length) {
                html += `
                <div class="iv-section">
                    <div class="iv-section-title suggestions"><span class="iv-section-icon">议</span>改进建议</div>
                    <ul class="iv-bullet-list suggestions">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ul>
                </div>`;
            }
        }

        // 问题分析表
        if (a.questions.length > 0) {
            html += `
            <div class="iv-section">
                <div class="iv-section-title"><span class="iv-section-icon">问</span>问题分析</div>
                <table class="iv-questions-table">
                    <thead>
                        <tr>
                            <th style="width:40%">问题</th>
                            <th style="width:45%">你的回答</th>
                            <th style="width:15%">回答质量</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${a.questions.map(q => `
                            <tr>
                                <td>${esc(q.question || '—')}</td>
                                <td>${esc(q.answer || '—')}</td>
                                <td><span class="q-quality ${qualityClass(q.quality)}">${esc(qualityLabel(q.quality))}</span></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>`;
        }

        return html;
    }

    function renderScoreBreakdown(breakdown) {
        const items = breakdown.map(b => {
            if (typeof b === 'string') return { label: b, score: null };
            const label = b.label || b.name || b.dimension || b.category || '';
            const score = b.score != null ? Number(b.score) : (b.value != null ? Number(b.value) : null);
            return { label, score };
        }).filter(b => b.label);

        if (!items.length) return '';

        return `
        <div class="score-breakdown">
            ${items.map(b => {
                const pct = (b.score != null && isFinite(b.score)) ? Math.max(0, Math.min(100, b.score)) : null;
                return `
                <div class="score-item">
                    <span class="score-item-label">${esc(b.label)}</span>
                    <div class="score-bar"><div class="score-fill" style="width:${pct != null ? pct : 0}%"></div></div>
                    ${pct != null ? `<span class="score-item-pct">${Math.round(pct)}</span>` : ''}
                </div>`;
            }).join('')}
        </div>`;
    }

    // ============ 渲染：历史复盘 ============

    function renderPastReviews() {
        const container = root.querySelector('#past-reviews');
        if (!container) return;

        if (!state.apiAvailable) {
            container.innerHTML = `
            <div class="past-reviews-head">
                <span class="past-reviews-title">历史复盘</span>
            </div>
            <div class="card">
                <div class="api-unavailable-card">
                    <span class="api-unavailable-icon">📋</span>
                    <span class="api-unavailable-title">日志功能即将上线</span>
                    <span class="api-unavailable-desc">后端日志接口尚未启用，历史复盘暂时无法加载。你仍可使用 AI 复盘功能分析面试表现。</span>
                    <span class="api-unavailable-tag">GET /journal/entries</span>
                </div>
            </div>`;
            return;
        }

        if (state.loadingReviews) {
            container.innerHTML = `
            <div class="past-reviews-head">
                <span class="past-reviews-title">历史复盘</span>
            </div>
            <div class="review-list">
                ${[0, 1, 2].map(() => '<div class="skeleton-row" style="height:72px;border-radius:10px"></div>').join('')}
            </div>`;
            return;
        }

        if (state.reviewsError && state.pastReviews.length === 0) {
            container.innerHTML = `
            <div class="past-reviews-head">
                <span class="past-reviews-title">历史复盘</span>
            </div>
            <div class="card">
                <div class="empty-card">
                    <span class="empty-emoji">⚠️</span>
                    <h3>加载失败</h3>
                    <p>${esc(state.reviewsError)}</p>
                    <button class="btn btn-ghost btn-sm" id="iv-retry-reviews" style="margin-top:0.8rem">重试</button>
                </div>
            </div>`;
            return;
        }

        if (state.pastReviews.length === 0) {
            container.innerHTML = `
            <div class="past-reviews-head">
                <span class="past-reviews-title">历史复盘</span>
            </div>
            <div class="card">
                <div class="empty-card">
                    <span class="empty-emoji">📝</span>
                    <h3>还没有复盘记录</h3>
                    <p>在上方填写面试笔记并点击「AI 复盘」，开始你的第一次面试复盘</p>
                </div>
            </div>`;
            return;
        }

        container.innerHTML = `
        <div class="past-reviews-head">
            <span class="past-reviews-title">历史复盘</span>
            <span class="past-reviews-count">共 ${state.pastReviews.length} 条</span>
        </div>
        <div class="review-list">
            ${state.pastReviews.map(e => renderReviewCard(e)).join('')}
        </div>`;
    }

    function renderReviewCard(entry) {
        const meta = entry.metadata || {};
        const company = meta.company || entry.title || '未知公司';
        const position = meta.position || '';
        const score = meta.score != null ? Number(meta.score) : null;
        const tier = score != null && isFinite(score) ? scoreTier(score) : 'none';
        const summary = meta.summary || '';
        const expanded = state.expandedId === entry.id;
        const deleting = state.deletingId === entry.id;

        const scoreBadge = score != null && isFinite(score)
            ? `<span class="review-score-badge ${tier}">${Math.round(score)} 分</span>`
            : `<span class="review-score-badge none">未评分</span>`;

        return `
        <div class="review-card ${expanded ? 'expanded' : ''}" data-id="${esc(String(entry.id))}">
            <div class="review-card-head" data-action="toggle">
                <div class="review-card-main">
                    <div class="review-card-row1">
                        <span class="review-company">${esc(company)}</span>
                        ${position ? `<span class="review-position">${esc(position)}</span>` : ''}
                        <span class="review-date">${esc(formatRelative(entry.created_at))}</span>
                    </div>
                    ${summary ? `<div class="review-preview">${esc(summary)}</div>` : ''}
                </div>
                ${scoreBadge}
                <span class="review-card-chevron">▶</span>
            </div>
            ${expanded ? `<div class="review-card-body">${renderReviewCardBody(entry, deleting)}</div>` : ''}
        </div>`;
    }

    function renderReviewCardBody(entry, deleting) {
        const meta = entry.metadata || {};
        const a = {
            score: meta.score != null ? Number(meta.score) : null,
            summary: meta.summary || '',
            strengths: meta.strengths || '',
            weaknesses: meta.weaknesses || '',
            suggestions: meta.suggestions || '',
            questions: normalizeQuestions(meta.questions),
            breakdown: Array.isArray(meta.breakdown) ? meta.breakdown : null,
        };

        let html = '';

        if (a.score != null) {
            const tier = scoreTier(a.score);
            html += `
            <div class="score-card" style="margin-top:0.6rem;margin-bottom:0.6rem;padding:0.9rem">
                <div class="score-circle score-${tier}" style="width:84px;height:84px;border-width:3px">
                    <span class="score-value" style="font-size:1.6rem">${esc(String(Math.round(a.score)))}</span>
                    <span class="score-label">评分</span>
                </div>
                ${a.breakdown ? renderScoreBreakdown(a.breakdown) : ''}
            </div>`;
        }

        if (a.summary) {
            html += `<div class="iv-section"><div class="iv-section-title"><span class="iv-section-icon">摘</span>总结</div><div class="iv-summary-text">${esc(a.summary)}</div></div>`;
        }
        if (a.strengths) {
            const list = Array.isArray(a.strengths) ? a.strengths : textToList(a.strengths);
            if (list.length) html += `<div class="iv-section"><div class="iv-section-title strengths"><span class="iv-section-icon">优</span>表现亮点</div><ul class="iv-bullet-list">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
        }
        if (a.weaknesses) {
            const list = Array.isArray(a.weaknesses) ? a.weaknesses : textToList(a.weaknesses);
            if (list.length) html += `<div class="iv-section"><div class="iv-section-title weaknesses"><span class="iv-section-icon">缺</span>待改进</div><ul class="iv-bullet-list weaknesses">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
        }
        if (a.suggestions) {
            const list = Array.isArray(a.suggestions) ? a.suggestions : textToList(a.suggestions);
            if (list.length) html += `<div class="iv-section"><div class="iv-section-title suggestions"><span class="iv-section-icon">议</span>改进建议</div><ul class="iv-bullet-list suggestions">${list.map(s => `<li>${esc(s)}</li>`).join('')}</ul></div>`;
        }
        if (a.questions.length > 0) {
            html += `
            <div class="iv-section">
                <div class="iv-section-title"><span class="iv-section-icon">问</span>问题分析</div>
                <table class="iv-questions-table">
                    <thead><tr><th style="width:40%">问题</th><th style="width:45%">你的回答</th><th style="width:15%">回答质量</th></tr></thead>
                    <tbody>
                        ${a.questions.map(q => `<tr><td>${esc(q.question || '—')}</td><td>${esc(q.answer || '—')}</td><td><span class="q-quality ${qualityClass(q.quality)}">${esc(qualityLabel(q.quality))}</span></td></tr>`).join('')}
                    </tbody>
                </table>
            </div>`;
        }

        if (entry.content) {
            html += `<div class="review-card-notes">${esc(entry.content)}</div>`;
        }

        html += `
        <div class="review-card-actions">
            <button class="btn btn-danger btn-sm" data-action="delete" data-id="${esc(String(entry.id))}" ${deleting ? 'disabled' : ''}>
                ${deleting ? '删除中...' : '删除'}
            </button>
            <span style="flex:1"></span>
            <span style="font-size:0.74rem;color:var(--ink-faint);align-self:center">${esc(formatDateTime(entry.created_at))}</span>
        </div>`;

        return html;
    }

    // ============ 渲染：周报 ============

    function renderWeeklyPanel() {
        const panel = root.querySelector('#panel-weekly');
        if (!panel) return;

        let html = '<div class="weekly-panel">';

        // 生成按钮卡
        html += `
        <div class="weekly-generate-card">
            <div class="weekly-generate-info">
                <div class="weekly-generate-title">本周求职周报</div>
                <div class="weekly-generate-desc">基于本周的投递记录、面试复盘与心情日志，AI 自动生成结构化周报，帮你回顾进展、规划下周行动。</div>
            </div>
            <button class="btn btn-ai" id="iv-generate-weekly" ${state.loadingWeekly ? 'disabled' : ''}>
                ${state.loadingWeekly ? '<span class="spinner" style="width:14px;height:14px;border-width:2px;margin-right:0.4rem;vertical-align:-2px"></span>生成中...' : '✨ 生成本周周报'}
            </button>
        </div>`;

        // 错误态
        if (state.weeklyError && !state.weekly && !state.loadingWeekly) {
            html += `
            <div class="card">
                <div class="empty-card">
                    <span class="empty-emoji">⚠️</span>
                    <h3>周报生成失败</h3>
                    <p>${esc(state.weeklyError)}</p>
                    <button class="btn btn-ghost btn-sm" id="iv-retry-weekly" style="margin-top:0.8rem">重试</button>
                </div>
            </div>`;
        }

        // 加载态
        if (state.loadingWeekly && !state.weekly) {
            html += `
            <div class="card">
                <div class="analyzing-state">
                    <div class="spinner"></div>
                    <span>AI 正在汇总本周数据...</span>
                    <span class="analyzing-tip">通常需要 15-40 秒，请稍候</span>
                </div>
            </div>`;
        }

        // 结果
        if (state.weekly) {
            html += renderWeeklyResult(state.weekly);
        }

        // 空态
        if (!state.weekly && !state.loadingWeekly && !state.weeklyError) {
            html += `
            <div class="card">
                <div class="empty-card">
                    <span class="empty-emoji">📅</span>
                    <h3>尚未生成本周周报</h3>
                    <p>点击上方按钮，AI 将为你生成本周求职周报</p>
                </div>
            </div>`;
        }

        html += '</div>';
        panel.innerHTML = html;
    }

    function renderWeeklyResult(w) {
        const highlights = Array.isArray(w.highlights) ? w.highlights :
            (w.highlights ? textToList(w.highlights) : []);
        const actions = Array.isArray(w.action_items) ? w.action_items :
            (w.action_items ? textToList(w.action_items) : []);

        let html = `<div class="card weekly-result-card">`;

        html += `
        <div class="card-header" style="margin-bottom:0.6rem">
            <span class="card-title">本周周报</span>
        </div>`;

        if (w.generated_at) {
            html += `<div class="weekly-meta">生成于 ${esc(formatDateTime(w.generated_at))}</div>`;
        }

        if (w.summary) {
            html += `
            <div class="iv-section">
                <div class="iv-section-title"><span class="iv-section-icon">摘</span>本周总结</div>
                <div class="iv-summary-text">${esc(w.summary)}</div>
            </div>`;
        }

        if (highlights.length) {
            html += `
            <div class="iv-section">
                <div class="iv-section-title"><span class="iv-section-icon">亮</span>本周亮点</div>
                <ul class="weekly-highlights">${highlights.map(h => `<li>${esc(h)}</li>`).join('')}</ul>
            </div>`;
        }

        if (actions.length) {
            html += `
            <div class="iv-section">
                <div class="iv-section-title suggestions"><span class="iv-section-icon">动</span>下周行动项</div>
                <ul class="weekly-actions-list">
                    ${actions.map((a, i) => `
                        <li class="weekly-action-item">
                            <input type="checkbox" id="iv-action-${i}" data-action="toggle-action" data-idx="${i}">
                            <label for="iv-action-${i}">${esc(typeof a === 'string' ? a : (a.text || a.title || JSON.stringify(a)))}</label>
                        </li>
                    `).join('')}
                </ul>
            </div>`;
        }

        if (!w.summary && !highlights.length && !actions.length) {
            html += `<div class="empty-card" style="padding:1.5rem"><span class="empty-emoji">📭</span><h3>本周暂无足够数据</h3><p>多记录面试复盘与投递，下周报告将更丰富</p></div>`;
        }

        html += `
        <div class="weekly-actions-footer">
            <button class="btn btn-primary btn-sm" id="iv-save-weekly" ${state.savingWeekly ? 'disabled' : ''}>
                ${state.savingWeekly ? '保存中...' : '保存为日志'}
            </button>
            <button class="btn btn-ghost btn-sm" id="iv-regenerate-weekly" ${state.loadingWeekly ? 'disabled' : ''}>重新生成</button>
        </div>`;

        html += `</div>`;
        return html;
    }

    // ============ 渲染入口 ============

    function rerenderForm() {
        const card = root.querySelector('#review-form-card');
        if (card) {
            card.innerHTML = renderReviewForm();
            bindFormEvents();
        }
    }

    function rerenderAll() {
        if (!root) return;
        root.innerHTML = renderShell();
        bindEvents();
        // 渲染各分区
        const formCard = root.querySelector('#review-form-card');
        if (formCard) {
            formCard.innerHTML = renderReviewForm();
            bindFormEvents();
        }
        renderAnalysisContainer();
        bindAnalysisEvents();
        renderPastReviews();
        bindPastReviewEvents();
        renderWeeklyPanel();
        bindWeeklyEvents();
        updateTabsUI();
        if (Motion && Motion.revealOnScroll) Motion.revealOnScroll();
    }

    function updateTabsUI() {
        root.querySelectorAll('#iv-tabs .tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === state.tab);
        });
        const pr = root.querySelector('#panel-review');
        const pw = root.querySelector('#panel-weekly');
        if (pr) pr.hidden = state.tab !== 'review';
        if (pw) pw.hidden = state.tab !== 'weekly';
    }

    // ============ 数据加载 ============

    async function loadApplications() {
        if (state.appsLoaded) return;
        try {
            const data = await API.get('/applications/');
            const list = Array.isArray(data) ? data : (data && data.items) || [];
            state.applications = list;
            state.appsLoaded = true;
            if (state.tab === 'review') rerenderForm();
        } catch (e) {
            // 静默失败，datalist 与下拉留空即可
            state.appsLoaded = true;
        }
    }

    async function loadPastReviews() {
        if (!state.apiAvailable) return;
        state.loadingReviews = true;
        state.reviewsError = null;
        renderPastReviews();
        try {
            const data = await API.get('/journal/entries?entry_type=' + encodeURIComponent(ENTRY_TYPE));
            const arr = Array.isArray(data) ? data : (data && data.items) || [];
            state.pastReviews = arr.map(normalizeEntry).filter(Boolean);
        } catch (e) {
            if (isApiMissingError(e)) {
                state.apiAvailable = false;
                state.pastReviews = [];
            } else {
                state.reviewsError = e.message || '加载历史复盘失败';
            }
        } finally {
            state.loadingReviews = false;
            renderPastReviews();
            bindPastReviewEvents();
        }
    }

    // ============ AI 复盘 ============

    function collectForm() {
        const companyEl = root.querySelector('#iv-company');
        const positionEl = root.querySelector('#iv-position');
        const appEl = root.querySelector('#iv-application');
        const notesEl = root.querySelector('#iv-notes');
        const f = {
            company: companyEl ? companyEl.value.trim() : '',
            position: positionEl ? positionEl.value.trim() : '',
            application_id: appEl ? appEl.value : '',
            notes: notesEl ? notesEl.value.trim() : '',
        };
        state.form = f;
        return f;
    }

    async function doAnalyze() {
        const f = collectForm();
        if (!f.notes) {
            API.toast('请先填写面试笔记', 'warn');
            const notesEl = root.querySelector('#iv-notes');
            if (notesEl) notesEl.focus();
            return;
        }

        state.analyzing = true;
        state.analysisError = null;
        state.analysis = null;
        rerenderForm();
        renderAnalysisContainer();
        bindAnalysisEvents();

        try {
            const body = {
                interview_notes: f.notes,
                position: f.position || undefined,
                company: f.company || undefined,
            };
            // 移除 undefined
            Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);

            const data = await API.post('/journal/review-interview', body, { timeout: 120000 });
            const normalized = normalizeAnalysis(data);
            if (!normalized) {
                throw new Error('AI 返回数据格式异常');
            }
            state.analysis = normalized;
            API.toast('AI 复盘完成', 'success');
        } catch (e) {
            const msg = e && e.message ? e.message : '未知错误';
            if (isApiMissingError(e)) {
                state.analysisError = 'AI 复盘接口尚未上线（' + msg + '）。你可以直接保存笔记为日志，待接口启用后再分析。';
            } else {
                state.analysisError = msg;
            }
            API.toast('AI 复盘失败: ' + msg, 'error', 5000);
        } finally {
            state.analyzing = false;
            rerenderForm();
            renderAnalysisContainer();
            bindAnalysisEvents();
        }
    }

    function resetAnalysis() {
        state.analysis = null;
        state.analysisError = null;
        renderAnalysisContainer();
        bindAnalysisEvents();
    }

    function clearForm() {
        state.form = { company: '', position: '', application_id: '', notes: '' };
        state.analysis = null;
        state.analysisError = null;
        rerenderForm();
        renderAnalysisContainer();
        bindAnalysisEvents();
    }

    // ============ 保存为日志 ============

    async function saveReviewAsEntry() {
        if (!state.analysis || state.savingReview) return;
        const f = collectForm();
        if (!f.notes && !state.analysis.summary) {
            API.toast('没有可保存的内容', 'warn');
            return;
        }

        state.savingReview = true;
        renderAnalysisContainer();
        bindAnalysisEvents();

        try {
            const a = state.analysis;
            const payload = {
                entry_type: ENTRY_TYPE,
                title: (f.company || '面试复盘') + (f.position ? ' · ' + f.position : ''),
                content: f.notes,
                application_id: f.application_id || null,
                metadata: {
                    company: f.company,
                    position: f.position,
                    summary: a.summary || '',
                    strengths: a.strengths || '',
                    weaknesses: a.weaknesses || '',
                    suggestions: a.suggestions || '',
                    questions: a.questions || [],
                    score: a.score != null ? a.score : null,
                    breakdown: a.breakdown || null,
                },
            };

            if (!state.apiAvailable) {
                throw Object.assign(new Error('日志接口尚未上线'), { status: 404 });
            }

            await API.post('/journal/entries', payload);
            API.toast('已保存为日志', 'success');
            // 重置分析区
            state.analysis = null;
            state.analysisError = null;
            renderAnalysisContainer();
            bindAnalysisEvents();
            // 刷新历史列表
            await loadPastReviews();
        } catch (e) {
            if (isApiMissingError(e)) {
                API.toast('日志功能尚未上线，保存失败', 'error', 5000);
            } else {
                API.toast('保存失败: ' + (e.message || '未知错误'), 'error');
            }
        } finally {
            state.savingReview = false;
            renderAnalysisContainer();
            bindAnalysisEvents();
        }
    }

    // ============ 历史复盘操作 ============

    function toggleExpand(id) {
        state.expandedId = (state.expandedId === id) ? null : id;
        renderPastReviews();
        bindPastReviewEvents();
    }

    async function deleteReview(id) {
        if (state.deletingId) return;
        if (!confirm('确定删除这条复盘记录？此操作不可撤销。')) return;

        state.deletingId = id;
        renderPastReviews();
        bindPastReviewEvents();

        try {
            await API.del('/journal/entries/' + encodeURIComponent(String(id)));
            API.toast('已删除', 'success');
            if (state.expandedId === id) state.expandedId = null;
            state.pastReviews = state.pastReviews.filter(e => e.id !== id);
            renderPastReviews();
            bindPastReviewEvents();
        } catch (e) {
            API.toast('删除失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.deletingId = null;
            renderPastReviews();
            bindPastReviewEvents();
        }
    }

    // ============ 周报 ============

    async function generateWeekly() {
        if (state.loadingWeekly) return;
        state.loadingWeekly = true;
        state.weeklyError = null;
        // 保留旧结果直到新结果到达？这里先清空以显示加载态
        state.weekly = null;
        renderWeeklyPanel();
        bindWeeklyEvents();

        try {
            const data = await API.get('/journal/weekly-summary', { timeout: 120000 });
            state.weekly = {
                summary: data.summary || '',
                highlights: Array.isArray(data.highlights) ? data.highlights :
                    (data.highlights ? textToList(data.highlights) : []),
                action_items: Array.isArray(data.action_items) ? data.action_items :
                    (data.action_items ? textToList(data.action_items) : []),
                generated_at: data.generated_at || new Date().toISOString(),
            };
            API.toast('周报生成完成', 'success');
        } catch (e) {
            const msg = e && e.message ? e.message : '未知错误';
            if (isApiMissingError(e)) {
                state.weeklyError = '周报接口尚未上线（' + msg + '）。请稍后再试。';
            } else {
                state.weeklyError = msg;
            }
            API.toast('周报生成失败: ' + msg, 'error', 5000);
        } finally {
            state.loadingWeekly = false;
            renderWeeklyPanel();
            bindWeeklyEvents();
        }
    }

    async function saveWeeklyAsEntry() {
        if (!state.weekly || state.savingWeekly) return;

        state.savingWeekly = true;
        renderWeeklyPanel();
        bindWeeklyEvents();

        try {
            const w = state.weekly;
            const payload = {
                entry_type: WEEKLY_TYPE,
                title: '本周求职周报 · ' + formatDate(new Date().toISOString()),
                content: w.summary || '',
                metadata: {
                    summary: w.summary || '',
                    highlights: w.highlights || [],
                    action_items: w.action_items || [],
                    generated_at: w.generated_at || new Date().toISOString(),
                },
            };

            if (!state.apiAvailable) {
                throw Object.assign(new Error('日志接口尚未上线'), { status: 404 });
            }

            await API.post('/journal/entries', payload);
            API.toast('周报已保存为日志', 'success');
        } catch (e) {
            if (isApiMissingError(e)) {
                API.toast('日志功能尚未上线，保存失败', 'error', 5000);
            } else {
                API.toast('保存失败: ' + (e.message || '未知错误'), 'error');
            }
        } finally {
            state.savingWeekly = false;
            renderWeeklyPanel();
            bindWeeklyEvents();
        }
    }

    // ============ 事件绑定 ============

    function bindEvents() {
        // Tab 切换
        const tabsEl = root.querySelector('#iv-tabs');
        if (tabsEl) {
            tabsEl.addEventListener('click', (e) => {
                const tab = e.target.closest('.tab');
                if (!tab) return;
                const key = tab.dataset.tab;
                if (key && key !== state.tab) {
                    switchTab(key);
                }
            });
        }
    }

    function switchTab(key) {
        state.tab = key;
        updateTabsUI();
        // 切换到周报时若未生成过则什么都不做（用户主动点击生成）
        // 切换到复盘时确保已加载历史
        if (key === 'review' && state.apiAvailable && state.pastReviews.length === 0 && !state.loadingReviews) {
            loadPastReviews();
        }
        // 重新绑定动态事件
        if (key === 'review') {
            renderAnalysisContainer();
            bindAnalysisEvents();
            renderPastReviews();
            bindPastReviewEvents();
        } else if (key === 'weekly') {
            renderWeeklyPanel();
            bindWeeklyEvents();
        }
    }

    function bindFormEvents() {
        const companyEl = root.querySelector('#iv-company');
        const positionEl = root.querySelector('#iv-position');
        const appEl = root.querySelector('#iv-application');
        const notesEl = root.querySelector('#iv-notes');

        if (companyEl) {
            companyEl.addEventListener('input', () => { state.form.company = companyEl.value; });
        }
        if (positionEl) {
            positionEl.addEventListener('input', () => { state.form.position = positionEl.value; });
        }
        if (appEl) {
            appEl.addEventListener('change', () => {
                state.form.application_id = appEl.value;
                // 联动填充公司/职位（若当前为空）
                const app = state.applications.find(a => String(a.id) === String(appEl.value));
                if (app) {
                    if (!state.form.company && app.company) {
                        state.form.company = app.company;
                        companyEl.value = app.company;
                    }
                    if (!state.form.position && app.position) {
                        state.form.position = app.position;
                        positionEl.value = app.position;
                    }
                }
            });
        }
        if (notesEl) {
            notesEl.addEventListener('input', () => { state.form.notes = notesEl.value; });
        }

        const analyzeBtn = root.querySelector('#iv-analyze-btn');
        if (analyzeBtn) analyzeBtn.addEventListener('click', doAnalyze);

        const clearBtn = root.querySelector('#iv-clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                if (state.form.notes || state.analysis) {
                    if (!confirm('确定清空当前表单与分析结果？')) return;
                }
                clearForm();
                API.toast('已清空', 'info', 1500);
            });
        }
    }

    function bindAnalysisEvents() {
        const saveBtn = root.querySelector('#iv-save-review-btn');
        if (saveBtn) saveBtn.addEventListener('click', saveReviewAsEntry);

        const reanalyzeBtn = root.querySelector('#iv-reanalyze-btn');
        if (reanalyzeBtn) reanalyzeBtn.addEventListener('click', resetAnalysis);
    }

    function bindPastReviewEvents() {
        const container = root.querySelector('#past-reviews');
        if (!container) return;

        // 卡片展开/折叠
        container.querySelectorAll('[data-action="toggle"]').forEach(el => {
            el.addEventListener('click', () => {
                const card = el.closest('.review-card');
                if (!card) return;
                const id = card.dataset.id;
                // 原始 id 可能是数字或字符串，统一比较
                const target = state.pastReviews.find(e => String(e.id) === String(id));
                if (target) toggleExpand(target.id);
            });
        });

        // 删除
        container.querySelectorAll('[data-action="delete"]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                deleteReview(id);
            });
        });

        // 重试
        const retryBtn = root.querySelector('#iv-retry-reviews');
        if (retryBtn) retryBtn.addEventListener('click', loadPastReviews);
    }

    function bindWeeklyEvents() {
        const genBtn = root.querySelector('#iv-generate-weekly');
        if (genBtn) genBtn.addEventListener('click', generateWeekly);

        const regenBtn = root.querySelector('#iv-regenerate-weekly');
        if (regenBtn) regenBtn.addEventListener('click', generateWeekly);

        const retryBtn = root.querySelector('#iv-retry-weekly');
        if (retryBtn) retryBtn.addEventListener('click', generateWeekly);

        const saveBtn = root.querySelector('#iv-save-weekly');
        if (saveBtn) saveBtn.addEventListener('click', saveWeeklyAsEntry);

        // 行动项勾选切换样式
        root.querySelectorAll('[data-action="toggle-action"]').forEach(cb => {
            cb.addEventListener('change', () => {
                const li = cb.closest('.weekly-action-item');
                if (li) li.classList.toggle('checked', cb.checked);
            });
        });
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        root.innerHTML = renderShell();
        bindEvents();

        // 渲染各分区初始内容
        const formCard = root.querySelector('#review-form-card');
        if (formCard) {
            formCard.innerHTML = renderReviewForm();
            bindFormEvents();
        }
        renderAnalysisContainer();
        bindAnalysisEvents();
        renderPastReviews();
        bindPastReviewEvents();
        renderWeeklyPanel();
        bindWeeklyEvents();

        // 并行加载：投递记录（用于 datalist）+ 历史复盘
        await Promise.all([loadApplications(), loadPastReviews()]);

        if (Motion && Motion.revealOnScroll) Motion.revealOnScroll();
    }

    function cleanup() {
        clearTimers();
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.interview = { mount: mount, cleanup: cleanup, title: '面试复盘' };
})(window);
