/**
 * 投递看板视图 — Job application Kanban board
 * 统计概览 + 跟进提醒 + 筛选 + 六列看板（拖拽改状态）+ 创建/编辑模态框 + 导入导出
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const Motion = global.OfferClawMotion;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const STATUSES = [
        { key: 'applied',    label: '已投递', color: 'var(--st-applied)' },
        { key: 'assessment', label: '笔试中', color: 'var(--st-assessment)' },
        { key: 'interview',  label: '面试中', color: 'var(--st-interview)' },
        { key: 'offer',      label: '已录用', color: 'var(--st-offer)' },
        { key: 'rejected',   label: '已拒绝', color: 'var(--st-rejected)' },
        { key: 'withdrawn',  label: '已撤回', color: 'var(--st-withdrawn)' },
    ];
    const STATUS_MAP = {};
    STATUSES.forEach(s => { STATUS_MAP[s.key] = s; });

    // 推进流水线：applied → assessment → interview → offer
    const PIPELINE = ['applied', 'assessment', 'interview', 'offer'];

    const REJECTION_STAGES = {
        'resume_rejected': '简历初筛挂',
        'assessment_failed': '笔试挂',
        'interview_1_failed': '一面挂',
        'interview_2_failed': '二面挂',
        'interview_3_failed': '三面挂',
        'hr_failed': 'HR 面挂',
        'offer_collapsed': 'offer 谈崩',
        'hc_empty': 'HC 没有',
        'self_withdraw': '主动放弃',
        'other': '其他',
    };

    const PRIORITY_LABELS = { high: '高', medium: '中', low: '低' };

    // 笔试/测评类型枚举（表单下拉）
    const ASSESSMENT_TYPES = ['AI测评', '在线笔试', '行测', '性格测试'];
    // 面试类型枚举（表单下拉 + 卡片徽标）
    const INTERVIEW_TYPES = ['AI面试', '真人面试'];

    // ============ 状态 ============

    const state = {
        applications: [],
        filters: { search: '', source: '', priority: '' },
        editing: null,
        initialStatus: 'applied',
        loading: true,
        viewMode: 'compact',   // 'card' | 'compact'
    };

    let root = null;
    let modalOverlay = null;
    let draggedId = null;
    let draggedSourceStatus = null;
    let dragPlaceholder = null;

    // ============ CSS ============

    const CSS_ID = 'kanban-styles';

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.kb-view { padding-bottom: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; }

/* --- 顶部一体化工具条 --- */
.kb-toolbar {
    display: flex;
    align-items: center;
    gap: 0.75rem 1rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
    padding: 0.7rem 0.9rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    box-shadow: var(--shadow-sm);
    flex-shrink: 0;
}
/* 标题组：眉标徽章 + 标题 + 副标题 横排 */
.kb-toolbar .view-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem 0.7rem;
    flex-wrap: wrap;
    flex-shrink: 0;
}
.kb-toolbar .view-title-row h1 {
    font-family: var(--font-serif);
    font-size: 1.2rem;
    font-weight: 900;
    color: var(--ink);
    margin: 0;
    letter-spacing: -0.3px;
}
.kb-toolbar .view-title-row .header-eyebrow {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 1.5px;
    line-height: 1.4;
    color: var(--olive);
    background: var(--olive-soft);
    padding: 0.16rem 0.55rem;
    border-radius: 5px;
    align-self: center;
    white-space: nowrap;
}
.kb-toolbar .view-title-row .view-subtitle {
    margin: 0;
    color: var(--ink-soft);
    font-size: 0.84rem;
    white-space: nowrap;
}
/* 搜索框 + 放大镜图标（紧凑定宽，吸向右侧区域） */
.kb-search-wrap {
    position: relative;
    display: inline-flex;
    align-items: center;
    width: 240px;
    max-width: 100%;
}
.kb-search-icon {
    position: absolute;
    left: 0.65rem;
    display: inline-flex;
    color: var(--ink-faint);
    pointer-events: none;
    transition: color 0.2s;
    z-index: 1;
}
.kb-search-input {
    width: 100%;
    padding: 0.42rem 0.75rem 0.42rem 1.9rem;
    border: 1px solid var(--line);
    border-radius: 7px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.85rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease), background 0.2s var(--ease);
}
.kb-search-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: var(--card);
}
.kb-search-input:focus ~ .kb-search-icon { color: var(--olive); }
/* 筛选 + 操作按钮组：吸右 */
.kb-filter-wrap {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-left: auto;
}
.kb-filter-select {
    padding: 0.42rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 7px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.82rem;
    font-family: inherit;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
}
.kb-filter-select:hover { border-color: var(--ink-ghost); }
.kb-filter-select:focus { outline: none; border-color: var(--olive); }
.kb-filter-actions {
    display: flex;
    gap: 0.4rem;
    padding-left: 0.75rem;
    border-left: 1px solid var(--line-soft);
}

/* --- 看板 --- */
.kb-board {
    display: flex;
    gap: 0.7rem;
    overflow-x: auto;
    overflow-y: hidden;
    padding-bottom: 0.4rem;
    min-height: 0;
    flex: 1;
}
.kb-column {
    flex: 0 0 260px;
    background: var(--paper-light);
    border: 1px solid var(--line);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    max-height: 100%;
}
.kb-column-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.55rem 0.75rem;
    border-top: 3px solid var(--col-color, var(--olive));
    border-bottom: 1px solid var(--line-soft);
    background: linear-gradient(135deg, color-mix(in srgb, var(--col-color, var(--olive)) 9%, var(--card)), var(--card) 70%);
    border-radius: 7px 7px 0 0;
    flex-shrink: 0;
}
.kb-column-title {
    font-family: var(--font-serif);
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 0.35rem;
}
.kb-col-dot {
    flex-shrink: 0;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--col-color, var(--olive));
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--col-color, var(--olive)) 20%, transparent);
}
.kb-column-count {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    font-weight: 700;
    color: color-mix(in srgb, var(--col-color, var(--olive)) 68%, var(--ink));
    background: color-mix(in srgb, var(--col-color, var(--olive)) 16%, transparent);
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    min-width: 22px;
    text-align: center;
}
.kb-column-body {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.55rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    transition: background 0.18s var(--ease);
    min-height: 0;
}
/* 列内滚动条 */
.kb-column-body::-webkit-scrollbar { width: 5px; }
.kb-column-body::-webkit-scrollbar-track { background: transparent; }
.kb-column-body::-webkit-scrollbar-thumb { background: var(--ink-ghost); border-radius: 3px; }
.kb-column-body.kb-drag-over {
    background: var(--olive-glow);
    outline: 2px dashed var(--olive);
    outline-offset: -4px;
}
.kb-col-empty {
    text-align: center;
    font-size: 0.75rem;
    color: var(--ink-ghost);
    padding: 1.2rem 0.5rem;
    font-style: italic;
}
.app-card, .kb-column-body {
    -webkit-user-select: none;
    user-select: none;
}

/* --- 卡片 --- */
.app-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-left: 3px solid var(--stc, var(--line));
    border-radius: 8px;
    padding: 0.65rem 0.75rem;
    cursor: grab;
    transition: box-shadow 0.2s var(--ease), transform 0.2s var(--ease), border-color 0.2s var(--ease);
    position: relative;
    overflow: hidden;
    flex-shrink: 0;
    min-height: 88px;
}
.app-card::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--stc, var(--line)), transparent 70%);
    opacity: 0.65;
}
.app-card:hover {
    box-shadow: 0 4px 14px color-mix(in srgb, var(--stc, var(--olive)) 18%, transparent), var(--shadow-sm);
    border-color: color-mix(in srgb, var(--stc, var(--olive)) 55%, var(--line));
    border-left-color: var(--stc, var(--olive));
    transform: translateY(-2px);
}
.app-card:active { cursor: grabbing; }
.app-card.card-dragging { opacity: 0.4; transform: rotate(2deg); }
.app-card.st-applied { --stc: var(--st-applied); }
.app-card.st-assessment { --stc: var(--st-assessment); }
.app-card.st-interview { --stc: var(--st-interview); }
.app-card.st-offer { --stc: var(--st-offer); }
.app-card.st-rejected { --stc: var(--st-rejected); }
.app-card.st-withdrawn { --stc: var(--st-withdrawn); }
.app-card.st-offer {
    background: linear-gradient(135deg, color-mix(in srgb, var(--st-offer) 6%, var(--card)), var(--card) 55%);
}
.app-card.st-rejected, .app-card.st-withdrawn { opacity: 0.88; }
.app-card.st-rejected:hover, .app-card.st-withdrawn:hover { opacity: 1; }
.card-top-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 0.15rem;
}
.card-company {
    font-family: var(--font-serif);
    font-size: 0.88rem;
    font-weight: 700;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 65%;
    min-width: 0;
    flex-shrink: 1;
    display: flex;
    align-items: center;
    gap: 0.3rem;
}
.card-dot {
    flex-shrink: 0;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--stc, var(--ink-faint));
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--stc, var(--ink-faint)) 18%, transparent);
}
.card-priority {
    font-size: 0.64rem;
    font-weight: 700;
    padding: 0.08rem 0.35rem;
    border-radius: 8px;
    flex-shrink: 0;
    line-height: 1.4;
}
.card-priority.priority-high { background: var(--st-rejected-soft); color: var(--st-rejected-deep); }
.card-priority.priority-medium { background: var(--st-assessment-soft); color: var(--st-assessment-deep); }
.card-priority.priority-low { background: var(--st-withdrawn-soft); color: var(--st-withdrawn-deep); }
.app-card.priority-high:hover {
    box-shadow: 0 4px 14px color-mix(in srgb, var(--st-rejected) 22%, transparent), var(--shadow-sm);
}
.card-position {
    font-size: 0.8rem;
    color: var(--ink-soft);
    margin-bottom: 0.3rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.4;
}
.card-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.74rem;
    color: var(--ink-faint);
    margin-bottom: 0.3rem;
}
.card-salary { color: var(--st-offer-deep); font-weight: 600; }
.card-badges { display: flex; gap: 0.35rem; flex-wrap: wrap; margin-bottom: 0.35rem; }
.card-badge {
    display: inline-flex; align-items: center; gap: 0.28rem;
    font-size: 0.68rem; font-weight: 600; padding: 0.15rem 0.5rem;
    border-radius: 6px; line-height: 1.5;
}
.card-badge .bdot { width: 0.5rem; height: 0.5rem; border-radius: 50%; flex-shrink: 0; }
.badge-at { background: color-mix(in srgb, var(--st-assessment) 12%, var(--card)); color: var(--st-assessment-deep); }
.badge-at .bdot { background: var(--st-assessment); }
.badge-it { background: color-mix(in srgb, var(--olive) 12%, var(--card)); color: color-mix(in srgb, var(--olive) 82%, var(--ink)); }
.badge-it .bdot { background: var(--olive); }
.badge-it.ai { background: color-mix(in srgb, var(--info) 12%, var(--card)); color: color-mix(in srgb, var(--info) 85%, var(--ink)); }
.badge-it.ai .bdot { background: var(--info); }
.card-countdown {
    font-size: 0.72rem;
    padding: 0.22rem 0.5rem;
    border-radius: 5px;
    background: color-mix(in srgb, var(--stc, var(--info)) 12%, var(--card));
    color: color-mix(in srgb, var(--stc, var(--info)) 80%, var(--ink));
    margin-bottom: 0.35rem;
    font-weight: 500;
}
.card-countdown.urgent {
    background: var(--st-rejected-soft);
    color: var(--st-rejected-deep);
    font-weight: 600;
}
.card-countdown.unset {
    background: var(--paper-deep);
    color: var(--ink-faint);
    font-style: italic;
    font-weight: 400;
}
.card-stale {
    font-size: 0.7rem;
    padding: 0.2rem 0.5rem;
    border-radius: 5px;
    background: color-mix(in srgb, var(--warn) 14%, transparent);
    color: color-mix(in srgb, var(--warn) 75%, var(--ink));
    margin-bottom: 0.35rem;
    font-weight: 600;
}
.card-actions {
    display: flex;
    gap: 0.35rem;
    padding-top: 0.35rem;
    border-top: 1px dashed var(--line-soft);
}
.card-btn {
    flex: 1;
    padding: 0.3rem 0.4rem;
    border: 1px solid var(--line);
    background: var(--paper-light);
    color: var(--ink-soft);
    border-radius: 5px;
    font-size: 0.74rem;
    font-family: inherit;
    cursor: pointer;
    transition: all 0.15s var(--ease);
}
.card-btn:hover {
    border-color: var(--olive);
    color: var(--olive-dark);
    background: var(--olive-soft);
}

/* --- 紧凑视图卡片 --- */
.app-card.compact {
    padding: 0.38rem 0.6rem;
    min-height: 0;
    flex-shrink: 0;
}
.app-card.compact .card-top-row {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    margin-bottom: 0;
}
.app-card.compact .card-company {
    font-size: 0.82rem;
    flex-shrink: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: none;
}
.app-card.compact .card-position {
    font-size: 0.76rem;
    color: var(--ink-soft);
    margin-bottom: 0;
    margin-left: 0.2rem;
    flex-shrink: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: none;
}
.app-card.compact .card-meta,
.app-card.compact .card-countdown,
.app-card.compact .card-stale,
.app-card.compact .card-actions {
    display: none;
}
.app-card.compact .card-priority {
    font-size: 0.6rem;
    padding: 0.05rem 0.3rem;
    margin-left: auto;
    flex-shrink: 0;
}
/* 紧凑视图卡片内的投递日期（同行内联，紧贴优先级左侧） */
.app-card.compact .compact-date {
    font-size: 0.62rem;
    color: var(--ink-faint);
    line-height: 1;
    white-space: nowrap;
    flex-shrink: 0;
    margin: 0 0.1rem 0 0.3rem;
    font-family: var(--font-mono);
}
/* 卡片视图：测评/面试徽标并入公司行，单行不换行 */
.app-card:not(.compact) .card-top-row .card-badges {
    display: inline-flex;
    flex-wrap: nowrap;
    margin-bottom: 0;
    align-items: center;
    margin-left: 0.3rem;
    flex-shrink: 0;
    white-space: nowrap;
}
.app-card:not(.compact) .card-top-row .card-badges .card-badge {
    flex-shrink: 0;
    white-space: nowrap;
}
/* 紧凑视图：徽标也并入同一行，不换行 */
.app-card.compact .card-badges {
    display: inline-flex;
    flex-wrap: nowrap;
    margin-bottom: 0;
    align-items: center;
    flex-shrink: 0;
    white-space: nowrap;
}
/* 紧凑视图列内更密 */
.kb-column-body.compact-mode {
    gap: 0.25rem;
    padding: 0.4rem;
}

/* --- 看板空态 --- */
.kb-board-empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.kb-board-empty .btn { margin-top: 0.8rem; }

/* --- 模态框 --- */
.kb-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(45, 42, 38, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 500;
    padding: 1rem;
}
.kb-modal {
    background: var(--card);
    border-radius: 12px;
    width: 100%;
    max-width: 720px;
    max-height: 88vh;
    display: flex;
    flex-direction: column;
    box-shadow: var(--shadow-lg);
    overflow: hidden;
}
.kb-modal-header {
    padding: 0.9rem 1.3rem;
    border-bottom: 1px solid var(--line);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.kb-modal-header h2 {
    font-family: var(--font-serif);
    font-size: 1.1rem;
    font-weight: 800;
    color: var(--ink);
}
.kb-modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    line-height: 1;
    cursor: pointer;
    color: var(--ink-faint);
    padding: 0.2rem 0.5rem;
    border-radius: 5px;
    transition: all 0.15s var(--ease);
}
.kb-modal-close:hover { background: var(--paper-deep); color: var(--ink); }
.kb-modal-body { padding: 1.1rem 1.3rem; overflow-y: auto; }
.kb-modal-footer {
    padding: 0.8rem 1.3rem;
    border-top: 1px solid var(--line);
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    background: var(--paper-light);
}
.kb-form-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.9rem;
}
.kb-field { display: flex; flex-direction: column; gap: 0.3rem; }
.kb-field.full { grid-column: 1 / -1; }
.kb-field label {
    font-size: 0.76rem;
    color: var(--ink-soft);
    font-weight: 500;
}
.kb-field input, .kb-field select, .kb-field textarea {
    padding: 0.5rem 0.65rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    font-size: 0.85rem;
    font-family: inherit;
    color: var(--ink);
    background: var(--paper-light);
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
    width: 100%;
}
.kb-field input:focus, .kb-field select:focus, .kb-field textarea:focus {
    outline: none;
    border-color: var(--olive);
    background: var(--card);
    box-shadow: 0 0 0 3px var(--olive-glow);
}
.kb-field textarea { resize: vertical; min-height: 64px; }
.kb-field-group {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.9rem;
    padding: 0.7rem 0.85rem;
    margin-top: 0.3rem;
    background: var(--paper-light);
    border: 1px dashed var(--line);
    border-radius: 8px;
}
.kb-field-group[hidden] { display: none; }
.kb-field-group .kb-field.full { grid-column: 1 / -1; }

@media (max-width: 900px) {
    .kb-form-grid, .kb-field-group { grid-template-columns: 1fr; }
    .kb-column { flex: 0 0 220px; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    /** 从对象中按优先级取第一个非空值（兼容多种字段命名） */
    function pick(obj) {
        if (!obj) return null;
        for (let i = 1; i < arguments.length; i++) {
            const v = obj[arguments[i]];
            if (v !== null && v !== undefined && v !== '') return v;
        }
        return null;
    }

    function toLocalInput(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '';
        const pad = n => String(n).padStart(2, '0');
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
            'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }

    function fromLocalInput(val) {
        if (!val) return null;
        const d = new Date(val);
        if (isNaN(d.getTime())) return null;
        return d.toISOString();
    }

    function formatDaysWaiting(appliedAt) {
        if (!appliedAt) return '';
        const d = new Date(appliedAt);
        if (isNaN(d.getTime())) return '';
        const diff = Date.now() - d.getTime();
        if (diff < 0) return '待投递';
        const days = Math.floor(diff / 86400000);
        if (days < 1) return '今天';
        if (days < 30) return days + '天前';
        if (days < 365) return Math.floor(days / 30) + '个月前';
        return Math.floor(days / 365) + '年前';
    }

    /** 投递时间：短格式 "MM-DD · 3天前"（跨年带年份），完整格式 "YYYY-MM-DD HH:mm" 用于悬浮提示 */
    function formatAppliedAt(appliedAt) {
        if (!appliedAt) return null;
        const d = new Date(appliedAt);
        if (isNaN(d.getTime())) return null;
        const pad = n => String(n).padStart(2, '0');
        const now = new Date();
        const md = pad(d.getMonth() + 1) + '-' + pad(d.getDate());
        const sameYear = d.getFullYear() === now.getFullYear();
        const datePart = sameYear ? md : String(d.getFullYear()).slice(2) + '-' + md;
        const rel = formatDaysWaiting(appliedAt);
        return {
            short: rel && rel !== '待投递' ? datePart + ' · ' + rel : datePart,
            dateOnly: datePart,  // 纯投递日期（MM-DD 或 YY-MM-DD），不附加「今天/X天前」等相对提示
            full: d.getFullYear() + '-' + md + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()),
        };
    }

    /** 已投递距今天数（用于停滞判定，与后端 STALE_THRESHOLD_DAYS=7 一致） */
    function staleDays(app) {
        if ((app.status || 'applied') !== 'applied') return 0;
        const appliedAt = pick(app, 'applied_at');
        if (!appliedAt) return 0;
        const d = new Date(appliedAt);
        if (isNaN(d.getTime())) return 0;
        return Math.floor((Date.now() - d.getTime()) / 86400000);
    }

    function formatCountdown(ts) {
        if (!ts) return { text: '', urgent: false };
        const d = new Date(ts);
        if (isNaN(d.getTime())) return { text: '', urgent: false };
        const diff = d.getTime() - Date.now();
        const abs = Math.abs(diff);
        const days = Math.floor(abs / 86400000);
        const hours = Math.floor((abs % 86400000) / 3600000);
        let text;
        if (diff > 0) {
            if (days >= 1) text = days + '天后';
            else if (hours >= 1) text = hours + '小时后';
            else text = '即将到来';
        } else {
            if (days >= 1) text = '逾期' + days + '天';
            else if (hours >= 1) text = '逾期' + hours + '小时';
            else text = '已到期';
        }
        return { text: text, urgent: diff < 86400000 };
    }

    // ============ 渲染 ============

    function renderSkeleton() {
        return `
        <div class="view-container kb-view">
            <div class="kb-toolbar">
                <div class="view-title-row">
                    <span class="header-eyebrow">DASHBOARD</span>
                    <h1>投递看板</h1>
                    <p class="view-subtitle">追踪所有求职投递的状态与进度</p>
                </div>
                <div class="kb-search-wrap">
                    <span class="kb-search-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
                    </span>
                    <input type="text" id="kb-search" class="kb-search-input" placeholder="搜索公司或职位...">
                </div>
                <div class="kb-filter-wrap">
                    <select id="kb-source-filter" class="kb-filter-select">
                        <option value="">全部来源</option>
                    </select>
                    <select id="kb-priority-filter" class="kb-filter-select">
                        <option value="">全部优先级</option>
                        <option value="high">高</option>
                        <option value="medium">中</option>
                        <option value="low">低</option>
                    </select>
                    <div class="kb-filter-actions">
                        <button class="btn btn-ghost btn-sm" id="kb-view-toggle" title="切换视图">
                            <svg id="view-icon-card" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>
                            <svg id="view-icon-compact" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                        </button>
                        <button class="btn btn-ghost btn-sm" id="kb-import-btn">导入</button>
                        <button class="btn btn-ghost btn-sm" id="kb-export-btn">导出</button>
                        <button class="btn btn-primary btn-sm" id="kb-create-btn">+ 新建投递</button>
                        <input type="file" id="kb-import-input" accept=".json,application/json" style="display:none">
                    </div>
                </div>
            </div>
            <div id="kb-board" class="kb-board">${renderBoardSkeleton()}</div>
        </div>`;
    }

    function renderBoardSkeleton() {
        return STATUSES.map(s => `
            <div class="kb-column">
                <div class="kb-column-header" style="--col-color:${s.color}">
                    <span class="kb-column-title">${s.label}</span>
                    <span class="kb-column-count">·</span>
                </div>
                <div class="kb-column-body">
                    <div class="skeleton-row" style="height:78px;margin-bottom:0.5rem"></div>
                    <div class="skeleton-row" style="height:78px"></div>
                </div>
            </div>`).join('');
    }

    function getFilteredApps() {
        let list = state.applications;
        const f = state.filters;
        if (f.search) {
            const q = f.search.toLowerCase();
            list = list.filter(a =>
                (a.company || '').toLowerCase().indexOf(q) >= 0 ||
                (a.position || '').toLowerCase().indexOf(q) >= 0
            );
        }
        if (f.source) {
            list = list.filter(a => (a.source || '') === f.source);
        }
        if (f.priority) {
            list = list.filter(a => (a.priority || 'medium') === f.priority);
        }
        return list;
    }

    function renderBoard() {
        const board = root.querySelector('#kb-board');
        if (!board) return;

        if (state.loading) {
            board.innerHTML = renderBoardSkeleton();
            return;
        }
        if (state.applications.length === 0) {
            board.innerHTML = `
                <div class="kb-board-empty empty-card">
                    <span class="empty-emoji">📋</span>
                    <h3>还没有投递记录</h3>
                    <p>点击「新建投递」添加第一条记录，或前往岗位搜索页加入</p>
                    <button class="btn btn-primary btn-sm" id="kb-empty-create">+ 新建投递</button>
                </div>`;
            const b = root.querySelector('#kb-empty-create');
            if (b) b.onclick = () => openCreateModal();
            return;
        }

        const filtered = getFilteredApps();
        if (filtered.length === 0) {
            board.innerHTML = `
                <div class="kb-board-empty empty-card">
                    <span class="empty-emoji">🔍</span>
                    <h3>没有匹配的记录</h3>
                    <p>尝试调整搜索或筛选条件</p>
                </div>`;
            return;
        }

        const grouped = {};
        STATUSES.forEach(s => { grouped[s.key] = []; });
        filtered.forEach(a => {
            const k = a.status || 'applied';
            if (grouped[k]) grouped[k].push(a);
        });
        // 每列按 sort_order 升序排列（拖拽排序持久化）
        Object.keys(grouped).forEach(k => {
            grouped[k].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
        });

        board.innerHTML = STATUSES.map(s => renderColumn(s, grouped[s.key])).join('');
    }

    function renderColumn(s, apps) {
        const isCompact = state.viewMode === 'compact';
        const cards = apps.map(renderCard).join('');
        return `
        <div class="kb-column" data-status="${s.key}">
            <div class="kb-column-header" style="--col-color:${s.color}">
                <span class="kb-column-title"><span class="kb-col-dot"></span>${s.label}</span>
                <span class="kb-column-count">${apps.length}</span>
            </div>
            <div class="kb-column-body${isCompact ? ' compact-mode' : ''}" data-status="${s.key}">
                ${cards || '<div class="kb-col-empty">拖拽卡片到此列，双击新建</div>'}
            </div>
        </div>`;
    }

    // ============ 卡片 ============

    // 环节徽标：测评类型（assessment） / 面试类型（AI面试 / 真人面试）
    function stageBadges(app) {
        const at = pick(app, 'assessment_type');
        const it = pick(app, 'interview_type');
        const b = [];
        if (app.status === 'assessment' && at) {
            b.push(`<span class="card-badge badge-at"><span class="bdot"></span>${esc(at)}</span>`);
        }
        if (app.status === 'interview' && it) {
            const ai = it === 'AI面试' ? ' ai' : '';
            b.push(`<span class="card-badge badge-it${ai}"><span class="bdot"></span>${esc(it)}</span>`);
        }
        return b.length ? `<div class="card-badges">${b.join('')}</div>` : '';
    }

    function renderCard(app) {
        const priority = pick(app, 'priority') || 'medium';
        const priorityLabel = PRIORITY_LABELS[priority] || priority;
        const status = app.status || 'applied';
        const isCompact = state.viewMode === 'compact';

        if (isCompact) {
            const cApplied = formatAppliedAt(pick(app, 'applied_at'));
            // 投递日期仅「已投递」状态显示，且只展示纯日期（MM-DD / YY-MM-DD）
            const appliedDate = (status === 'applied' && cApplied)
                ? `<span class="compact-date" title="投递于 ${esc(cApplied.full)}">${esc(cApplied.dateOnly)}</span>` : '';
            const badges = stageBadges(app);
            return `
            <div class="app-card compact st-${status} priority-${priority}" draggable="true" data-id="${esc(app.id)}" title="${esc(app.company || '未知公司')} — ${esc(app.position || '未知职位')}&#10;投递于 ${esc(cApplied ? cApplied.full : '未记录')}&#10;双击编辑详情">
                <div class="card-top-row">
                    <span class="card-company"><span class="card-dot"></span>${esc(app.company || '未知公司')}</span>
                    <span class="card-position">${esc(app.position || '未知职位')}</span>
                    ${badges}
                    ${appliedDate}
                    <span class="card-priority priority-${priority}">${esc(priorityLabel)}</span>
                </div>
            </div>`;
        }

        const salary = pick(app, 'salary_range', 'offer_salary');
        const applied = formatAppliedAt(pick(app, 'applied_at'));

        // 倒计时（按状态显示相关字段；缺失时给出可操作的提示，与跟进提醒口径一致）
        const countdowns = [];
        if (status === 'assessment') {
            const dl = pick(app, 'assessment_deadline');
            if (dl) countdowns.push({ label: '笔试', ts: dl });
            else countdowns.push({ label: '笔试截止时间未设置', ts: null });
        }
        if (status === 'interview') {
            const it = pick(app, 'interview_time', 'next_interview_at');
            if (it) countdowns.push({ label: '面试', ts: it });
            else countdowns.push({ label: '面试时间未安排', ts: null });
        }
        if (status === 'offer') {
            const od = pick(app, 'offer_deadline');
            if (od) countdowns.push({ label: 'Offer', ts: od });
        }

        // 停滞标记：已投递超过 7 天未回复（与统计栏 / 跟进提醒「停滞投递」一致）
        const sDays = staleDays(app);
        const staleHtml = sDays >= 7
            ? `<div class="card-stale" title="超过 7 天未回复，建议跟进">⏰ 停滞 ${sDays} 天</div>`
            : '';

        const cdHtml = countdowns.map(c => {
            if (!c.ts) return `<div class="card-countdown unset">${esc(c.label)}</div>`;
            const cd = formatCountdown(c.ts);
            const cls = cd.urgent ? 'card-countdown urgent' : 'card-countdown';
            return `<div class="${cls}">${esc(c.label)}: ${esc(cd.text)}</div>`;
        }).join('');

        const canAdvance = PIPELINE.indexOf(status) >= 0 && PIPELINE.indexOf(status) < PIPELINE.length - 1;

        return `
        <div class="app-card st-${status} priority-${priority}" draggable="true" data-id="${esc(app.id)}" title="双击编辑详情">
            <div class="card-top-row">
                <span class="card-company" title="${esc(app.company)}"><span class="card-dot"></span>${esc(app.company || '未知公司')}</span>
                ${stageBadges(app)}
                <span class="card-priority priority-${priority}">${esc(priorityLabel)}</span>
            </div>
            <div class="card-position" title="${esc(app.position)}">${esc(app.position || '未知职位')}</div>
            <div class="card-meta">
                ${salary ? `<span class="card-salary">${esc(salary)}</span>` : '<span></span>'}
                <span class="card-date" title="投递于 ${esc(applied ? applied.full : '未记录')}">${esc(applied ? applied.short : '')}</span>
            </div>
            ${staleHtml}
            ${cdHtml}
            <div class="card-actions">
                <button class="card-btn" data-action="edit">编辑</button>
                <button class="card-btn" data-action="advance" ${canAdvance ? '' : 'disabled'}>推进</button>
            </div>
        </div>`;
    }

    // ============ 模态框 ============

    function renderModal() {
        const a = state.editing || {};
        // 编辑用记录状态；新建用双击列传入的初始状态
        const status = a.status || state.initialStatus || 'applied';
        const priority = a.priority || 'medium';
        const sources = Array.from(new Set(state.applications.map(x => x.source).filter(Boolean))).sort();

        const roundLabels = ['', '一面', '二面', '三面', 'HR面', '加面'];
        const interviewRound = pick(a, 'interview_round');
        const interviewType = pick(a, 'interview_type');
        const assessmentType = pick(a, 'assessment_type');
        const offerResp = pick(a, 'offer_responded', 'offer_status');
        const rejStage = pick(a, 'rejection_stage');

        return `
        <div class="modal-overlay kb-modal-overlay" id="kb-modal-overlay">
            <div class="modal kb-modal" role="dialog" aria-modal="true">
                <div class="kb-modal-header">
                    <h2>${state.editing ? '编辑投递' : '新建投递'}</h2>
                    <button class="kb-modal-close" data-action="close" aria-label="关闭">&times;</button>
                </div>
                <div class="kb-modal-body">
                    <datalist id="kb-sources">
                        ${sources.map(s => `<option value="${esc(s)}">`).join('')}
                    </datalist>
                    <form class="kb-form" id="kb-form" onsubmit="return false">
                        <div class="kb-form-grid">
                            <div class="kb-field">
                                <label>公司 *</label>
                                <input name="company" required value="${esc(a.company || '')}">
                            </div>
                            <div class="kb-field">
                                <label>职位 *</label>
                                <input name="position" required value="${esc(a.position || '')}">
                            </div>
                            <div class="kb-field">
                                <label>状态</label>
                                <select name="status" id="kb-field-status">
                                    ${STATUSES.map(s => `<option value="${s.key}" ${s.key === status ? 'selected' : ''}>${s.label}</option>`).join('')}
                                </select>
                            </div>
                            <div class="kb-field">
                                <label>优先级</label>
                                <select name="priority">
                                    <option value="high" ${priority === 'high' ? 'selected' : ''}>高</option>
                                    <option value="medium" ${priority === 'medium' ? 'selected' : ''}>中</option>
                                    <option value="low" ${priority === 'low' ? 'selected' : ''}>低</option>
                                </select>
                            </div>
                            <div class="kb-field">
                                <label>来源</label>
                                <input name="source" list="kb-sources" value="${esc(a.source || '')}" placeholder="如 Boss直聘 / 内推">
                            </div>
                            <div class="kb-field">
                                <label>岗位链接</label>
                                <input name="job_url" value="${esc(a.job_url || '')}" placeholder="https://">
                            </div>
                            <div class="kb-field">
                                <label>投递时间</label>
                                <input type="datetime-local" name="applied_at" value="${esc(toLocalInput(pick(a, 'applied_at')))}">
                            </div>
                            <div class="kb-field">
                                <label>薪资范围</label>
                                <input name="salary_range" value="${esc(pick(a, 'salary_range', 'offer_salary') || '')}" placeholder="如 25-40K·14薪">
                            </div>
                            <div class="kb-field">
                                <label>地点</label>
                                <input name="location" value="${esc(pick(a, 'location', 'offer_location') || '')}">
                            </div>
                            <div class="kb-field">
                                <label>联系人</label>
                                <input name="contact_name" value="${esc(pick(a, 'contact_name', 'hr_contact') || '')}" placeholder="HR 联系方式">
                            </div>

                            <div class="kb-field-group kb-group-assessment" data-show="assessment">
                                <div class="kb-field">
                                    <label>测评类型</label>
                                    <select name="assessment_type">
                                        <option value="">未选择</option>
                                        ${[...ASSESSMENT_TYPES, ...(assessmentType && ASSESSMENT_TYPES.indexOf(assessmentType) < 0 ? [assessmentType] : [])]
                                            .map(t => `<option value="${esc(t)}" ${assessmentType === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="kb-field">
                                    <label>测评截止</label>
                                    <input type="datetime-local" name="assessment_deadline" value="${esc(toLocalInput(pick(a, 'assessment_deadline')))}">
                                </div>
                            </div>

                            <div class="kb-field-group kb-group-interview" data-show="interview">
                                <div class="kb-field">
                                    <label>面试轮次</label>
                                    <select name="interview_round">
                                        <option value="">未选择</option>
                                        ${[1, 2, 3, 4, 5].map(n => `<option value="${n}" ${interviewRound === n ? 'selected' : ''}>${roundLabels[n]}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="kb-field">
                                    <label>面试时间</label>
                                    <input type="datetime-local" name="interview_time" value="${esc(toLocalInput(pick(a, 'interview_time', 'next_interview_at')))}">
                                </div>
                                <div class="kb-field">
                                    <label>面试类型</label>
                                    <select name="interview_type">
                                        <option value="">未选择</option>
                                        ${[...INTERVIEW_TYPES, ...(interviewType && INTERVIEW_TYPES.indexOf(interviewType) < 0 ? [interviewType] : [])]
                                            .map(t => `<option value="${esc(t)}" ${interviewType === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
                                    </select>
                                </div>
                            </div>

                            <div class="kb-field-group kb-group-offer" data-show="offer">
                                <div class="kb-field">
                                    <label>Offer 薪资</label>
                                    <input name="offer_salary" value="${esc(pick(a, 'offer_salary') || '')}">
                                </div>
                                <div class="kb-field">
                                    <label>Offer 截止</label>
                                    <input type="datetime-local" name="offer_deadline" value="${esc(toLocalInput(pick(a, 'offer_deadline')))}">
                                </div>
                                <div class="kb-field full">
                                    <label>Offer 回复</label>
                                    <select name="offer_responded">
                                        <option value="">未选择</option>
                                        <option value="pending" ${offerResp === 'pending' ? 'selected' : ''}>待回复</option>
                                        <option value="accepted" ${offerResp === 'accepted' ? 'selected' : ''}>已接受</option>
                                        <option value="declined" ${offerResp === 'declined' ? 'selected' : ''}>已拒绝</option>
                                    </select>
                                </div>
                            </div>

                            <div class="kb-field-group kb-group-rejected" data-show="rejected">
                                <div class="kb-field full">
                                    <label>拒绝环节</label>
                                    <select name="rejection_stage">
                                        <option value="">未选择</option>
                                        ${Object.keys(REJECTION_STAGES).map(k => `<option value="${k}" ${rejStage === k ? 'selected' : ''}>${REJECTION_STAGES[k]}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="kb-field full">
                                    <label>拒绝原因</label>
                                    <input name="rejection_reason" value="${esc(pick(a, 'rejection_reason') || '')}" placeholder="补充说明">
                                </div>
                            </div>

                            <div class="kb-field full">
                                <label>备注</label>
                                <textarea name="notes" placeholder="面试感受、HR 沟通要点等">${esc(a.notes || '')}</textarea>
                            </div>
                        </div>
                    </form>
                </div>
                <div class="kb-modal-footer">
                    ${state.editing ? '<button class="btn btn-danger btn-sm" data-action="delete">删除</button>' : ''}
                    <div style="flex:1"></div>
                    <button class="btn btn-ghost btn-sm" data-action="cancel">取消</button>
                    <button class="btn btn-primary btn-sm kb-modal-save" data-action="save">${state.editing ? '保存' : '创建'}</button>
                </div>
            </div>
        </div>`;
    }

    function updateModalGroups() {
        if (!modalOverlay) return;
        const status = modalOverlay.querySelector('#kb-field-status').value;
        modalOverlay.querySelectorAll('.kb-field-group').forEach(g => {
            g.hidden = g.dataset.show !== status;
        });
    }

    function openCreateModal(initialStatus) {
        state.editing = null;
        state.initialStatus = initialStatus || 'applied';
        showModal();
    }

    function openEditModal(app) {
        state.editing = app;
        showModal();
    }

    function showModal() {
        if (modalOverlay) closeModal(true);
        const wrapper = document.createElement('div');
        wrapper.innerHTML = renderModal();
        modalOverlay = wrapper.firstElementChild;
        document.body.appendChild(modalOverlay);
        updateModalGroups();
        // 触发淡入
        requestAnimationFrame(() => modalOverlay.classList.add('show'));
        // 绑定事件
        modalOverlay.querySelector('#kb-field-status').addEventListener('change', updateModalGroups);
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });
        modalOverlay.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = btn.dataset.action;
                if (action === 'close' || action === 'cancel') closeModal();
                else if (action === 'save') saveModal();
                else if (action === 'delete') deleteCurrent();
            });
        });
        document.addEventListener('keydown', onModalKeydown);
        // 聚焦公司字段
        const companyInput = modalOverlay.querySelector('input[name="company"]');
        if (companyInput) companyInput.focus();
    }

    function onModalKeydown(e) {
        if (e.key === 'Escape') closeModal();
    }

    function closeModal(skipEvent) {
        if (!modalOverlay) return;
        const el = modalOverlay;
        modalOverlay = null;
        el.classList.remove('show');
        setTimeout(() => el.remove(), 220);
        if (!skipEvent) document.removeEventListener('keydown', onModalKeydown);
        state.editing = null;
        state.initialStatus = 'applied';
    }

    function collectFormData() {
        const form = modalOverlay.querySelector('#kb-form');
        const fd = new FormData(form);
        const data = {};
        // 前端展示字段名 → 后端 API 字段名映射
        // （前端表单用更口语化的 name，后端 schema 用既有语义字段，避免提交被静默丢弃）
        const FIELD_MAP = {
            'salary_range': 'offer_salary',
            'location': 'offer_location',
            'contact_name': 'hr_contact',
            'interview_time': 'next_interview_at',
        };
        const datetimeFields = ['applied_at', 'assessment_deadline', 'next_interview_at', 'offer_deadline'];

        for (const [k, v] of fd.entries()) {
            const key = FIELD_MAP[k] || k;
            if (datetimeFields.indexOf(key) >= 0) {
                const iso = fromLocalInput(v);
                if (iso) data[key] = iso;
            } else if (key === 'interview_round') {
                if (v !== '') data[key] = parseInt(v, 10);
            } else {
                if (v !== '') data[key] = v;
            }
        }
        // 始终发送状态与优先级
        data.status = fd.get('status') || 'applied';
        data.priority = fd.get('priority') || 'medium';
        return data;
    }

    async function saveModal() {
        const data = collectFormData();
        if (!data.company || !data.position) {
            API.toast('公司和职位不能为空', 'warn');
            return;
        }
        const btn = modalOverlay.querySelector('.kb-modal-save');
        if (btn) btn.disabled = true;
        try {
            if (state.editing) {
                await API.put('/applications/' + encodeURIComponent(state.editing.id), data);
                API.toast('已更新投递记录', 'success');
            } else {
                await API.post('/applications/', data);
                API.toast('已创建投递记录', 'success');
            }
            closeModal();
            await loadAll();
        } catch (e) {
            API.toast('保存失败: ' + e.message, 'error');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async function deleteCurrent() {
        if (!state.editing) return;
        if (!confirm('确定删除这条投递记录？此操作不可撤销。')) return;
        try {
            await API.del('/applications/' + encodeURIComponent(state.editing.id));
            API.toast('已删除', 'success');
            closeModal();
            await loadAll();
        } catch (e) {
            API.toast('删除失败: ' + e.message, 'error');
        }
    }

    // ============ 状态变更 ============

    function advanceStatus(app) {
        const idx = PIPELINE.indexOf(app.status);
        if (idx < 0 || idx >= PIPELINE.length - 1) {
            API.toast('当前状态无法继续推进', 'warn');
            return;
        }
        const next = PIPELINE[idx + 1];
        changeStatus(app.id, next);
    }

    async function changeStatus(id, newStatus) {
        const app = state.applications.find(a => a.id === id);
        if (!app) return;
        const oldStatus = app.status;
        if (oldStatus === newStatus) return;

        // 乐观更新
        app.status = newStatus;
        renderBoard();

        try {
            await API.patch('/applications/' + encodeURIComponent(id) + '/status?new_status=' + encodeURIComponent(newStatus));
            API.toast('状态已更新为「' + (STATUS_MAP[newStatus] && STATUS_MAP[newStatus].label || newStatus) + '」', 'success');
        } catch (e) {
            // 回滚
            app.status = oldStatus;
            renderBoard();
            API.toast('状态更新失败: ' + e.message, 'error');
        }
    }

    // ============ 排序 ============

    /**
     * 计算拖拽插入位置（基于鼠标 Y 坐标）
     */
    function getDropIndex(colBody, clientY) {
        const cards = Array.from(colBody.querySelectorAll('.app-card:not(.card-dragging)'));
        for (let i = 0; i < cards.length; i++) {
            const rect = cards[i].getBoundingClientRect();
            const mid = rect.top + rect.height / 2;
            if (clientY < mid) return i;
        }
        return cards.length;
    }

    /**
     * 同列或跨列排序：根据目标列的期望顺序重新分配 sort_order 并持久化
     */
    async function reorderInColumn(targetStatus, draggedAppId, insertIndex) {
        const appsInColumn = state.applications
            .filter(a => (a.status || 'applied') === targetStatus)
            .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));

        // 把拖拽项移到指定位置
        const draggedIndex = appsInColumn.findIndex(a => a.id === draggedAppId);
        if (draggedIndex >= 0) {
            const [item] = appsInColumn.splice(draggedIndex, 1);
            // 插入索引需考虑移除后的偏移
            const adjustedIndex = insertIndex > draggedIndex ? insertIndex - 1 : insertIndex;
            appsInColumn.splice(adjustedIndex, 0, item);
        } else if (draggedAppId) {
            // 跨列移入：从全局列表找到并加入
            const item = state.applications.find(a => a.id === draggedAppId);
            if (item) appsInColumn.splice(insertIndex, 0, item);
        }

        // 重新分配 sort_order（步长 10，留间隙）
        const orders = appsInColumn.map((a, idx) => ({
            id: a.id,
            sort_order: idx * 10,
        }));

        // 乐观更新内存
        orders.forEach(o => {
            const app = state.applications.find(a => a.id === o.id);
            if (app) app.sort_order = o.sort_order;
        });
        renderBoard();

        try {
            await API.patch('/applications/reorder', orders);
        } catch (e) {
            API.toast('排序保存失败: ' + e.message, 'error');
            // 失败后下次加载会恢复后端顺序
            await loadApplications();
            renderBoard();
        }
    }

    // ============ 导入导出 ============

    function handleExport() {
        if (state.applications.length === 0) {
            API.toast('暂无记录可导出', 'warn');
            return;
        }
        const data = JSON.stringify(state.applications, null, 2);
        const blob = new Blob([data], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'offerclaw_applications_' + new Date().toISOString().slice(0, 10) + '.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        API.toast('已导出 ' + state.applications.length + ' 条记录', 'success');
    }

    function handleImportFile(file) {
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async (e) => {
            let items;
            try {
                items = JSON.parse(e.target.result);
            } catch (err) {
                API.toast('文件解析失败：不是有效的 JSON', 'error');
                return;
            }
            if (!Array.isArray(items)) {
                API.toast('文件格式错误：需要 JSON 数组', 'error');
                return;
            }
            try {
                const res = await API.post('/applications/batch', items);
                const n = (res && res.imported) != null ? res.imported : items.length;
                API.toast('已导入 ' + n + ' 条记录', 'success');
                await loadAll();
            } catch (err) {
                API.toast('导入失败: ' + err.message, 'error');
            }
        };
        reader.onerror = () => API.toast('文件读取失败', 'error');
        reader.readAsText(file);
    }

    // ============ 数据加载 ============

    async function loadApplications() {
        try {
            const data = await API.get('/applications/');
            state.applications = Array.isArray(data) ? data : (data && data.items) || [];
        } catch (e) {
            state.applications = [];
            API.toast('加载投递列表失败: ' + e.message, 'error');
        }
    }

    async function loadAll() {
        state.loading = true;
        renderBoard();
        await loadApplications();
        state.loading = false;
        updateSourceFilter();
        renderBoard();
        if (Motion && Motion.revealOnScroll) Motion.revealOnScroll();
    }

    function updateSourceFilter() {
        const sel = root.querySelector('#kb-source-filter');
        if (!sel) return;
        const current = sel.value;
        const sources = Array.from(new Set(state.applications.map(a => a.source).filter(Boolean))).sort();
        sel.innerHTML = '<option value="">全部来源</option>' +
            sources.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
        sel.value = current;
    }

    // ============ 事件绑定 ============

    function bindEvents() {
        // 搜索
        const searchEl = root.querySelector('#kb-search');
        let searchTimer = null;
        searchEl.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                state.filters.search = searchEl.value.trim();
                renderBoard();
            }, 200);
        });

        // 来源筛选
        const sourceSel = root.querySelector('#kb-source-filter');
        sourceSel.addEventListener('change', () => {
            state.filters.source = sourceSel.value;
            renderBoard();
        });

        // 优先级筛选
        const priSel = root.querySelector('#kb-priority-filter');
        priSel.addEventListener('change', () => {
            state.filters.priority = priSel.value;
            renderBoard();
        });

        // 按钮
        root.querySelector('#kb-create-btn').addEventListener('click', openCreateModal);
        root.querySelector('#kb-export-btn').addEventListener('click', handleExport);
        root.querySelector('#kb-import-btn').addEventListener('click', () => {
            root.querySelector('#kb-import-input').click();
        });
        const importInput = root.querySelector('#kb-import-input');
        importInput.addEventListener('change', () => {
            handleImportFile(importInput.files[0]);
            importInput.value = '';
        });

        // 视图切换
        const viewToggle = root.querySelector('#kb-view-toggle');
        if (viewToggle) {
            viewToggle.addEventListener('click', () => {
                state.viewMode = state.viewMode === 'card' ? 'compact' : 'card';
                const iconCard = viewToggle.querySelector('#view-icon-card');
                const iconCompact = viewToggle.querySelector('#view-icon-compact');
                if (iconCard) iconCard.style.display = state.viewMode === 'card' ? '' : 'none';
                if (iconCompact) iconCompact.style.display = state.viewMode === 'compact' ? '' : 'none';
                viewToggle.title = state.viewMode === 'card' ? '切换到紧凑视图' : '切换到卡片视图';
                renderBoard();
            });
        }

        // 看板事件委托（绑定在持久化的 board 元素上）
        const board = root.querySelector('#kb-board');
        bindBoardEvents(board);
    }

    function bindBoardEvents(board) {
        // 卡片操作
        board.addEventListener('click', (e) => {
            const btn = e.target.closest('.card-btn');
            if (!btn || btn.disabled) return;
            const card = btn.closest('.app-card');
            if (!card) return;
            const id = card.dataset.id;
            const app = state.applications.find(a => a.id === id);
            if (!app) return;
            const action = btn.dataset.action;
            if (action === 'edit') openEditModal(app);
            else if (action === 'advance') advanceStatus(app);
        });

        // 双击卡片直接编辑；双击列空白处按该列状态新建
        board.addEventListener('dblclick', (e) => {
            if (e.target.closest('.card-btn')) return;
            const card = e.target.closest('.app-card');
            if (card) {
                const id = card.dataset.id;
                const app = state.applications.find(a => a.id === id);
                if (app) openEditModal(app);
                return;
            }
            const col = e.target.closest('.kb-column-body');
            if (col && col.dataset.status) {
                openCreateModal(col.dataset.status);
            }
        });

        // 拖拽：支持同列排序 + 跨列改状态
        board.addEventListener('dragstart', (e) => {
            const card = e.target.closest('.app-card');
            if (!card) return;
            draggedId = card.dataset.id;
            const app = state.applications.find(a => a.id === draggedId);
            draggedSourceStatus = app ? (app.status || 'applied') : null;
            card.classList.add('card-dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', draggedId); } catch (_) {}
        });

        board.addEventListener('dragend', (e) => {
            const card = e.target.closest('.app-card');
            if (card) card.classList.remove('card-dragging');
            draggedId = null;
            draggedSourceStatus = null;
            board.querySelectorAll('.kb-drag-over').forEach(el => el.classList.remove('kb-drag-over'));
            // 清理占位条
            if (dragPlaceholder && dragPlaceholder.parentNode) {
                dragPlaceholder.parentNode.removeChild(dragPlaceholder);
            }
            dragPlaceholder = null;
        });

        board.addEventListener('dragover', (e) => {
            const col = e.target.closest('.kb-column-body');
            if (!col) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';

            // 同列时显示插入占位条
            if (draggedSourceStatus && col.dataset.status === draggedSourceStatus) {
                const idx = getDropIndex(col, e.clientY);
                if (!dragPlaceholder) {
                    dragPlaceholder = document.createElement('div');
                    dragPlaceholder.className = 'kb-drag-placeholder';
                    dragPlaceholder.style.cssText = 'height:3px;background:var(--olive);border-radius:2px;margin:4px 0;pointer-events:none;transition:none;';
                }
                const cards = Array.from(col.querySelectorAll('.app-card:not(.card-dragging)'));
                if (idx >= cards.length) {
                    col.appendChild(dragPlaceholder);
                } else {
                    col.insertBefore(dragPlaceholder, cards[idx]);
                }
            }
        });

        board.addEventListener('dragenter', (e) => {
            const col = e.target.closest('.kb-column-body');
            if (col) col.classList.add('kb-drag-over');
        });

        board.addEventListener('dragleave', (e) => {
            const col = e.target.closest('.kb-column-body');
            if (col && !col.contains(e.relatedTarget)) {
                col.classList.remove('kb-drag-over');
            }
        });

        board.addEventListener('drop', (e) => {
            e.preventDefault();
            const col = e.target.closest('.kb-column-body');
            if (!col) return;
            col.classList.remove('kb-drag-over');
            if (dragPlaceholder && dragPlaceholder.parentNode) {
                dragPlaceholder.parentNode.removeChild(dragPlaceholder);
            }
            dragPlaceholder = null;

            const id = draggedId || (function () {
                try { return e.dataTransfer.getData('text/plain'); } catch (_) { return ''; }
            })();
            const newStatus = col.dataset.status;
            if (!id || !newStatus) return;

            const app = state.applications.find(a => a.id === id);
            if (!app) return;

            const insertIndex = getDropIndex(col, e.clientY);

            if (draggedSourceStatus === newStatus) {
                // 同列：只排序
                reorderInColumn(newStatus, id, insertIndex);
            } else {
                // 跨列：先改状态，再排序
                const oldStatus = app.status;
                app.status = newStatus;
                // 清理原列 sort_order 避免冲突
                app.sort_order = 999999;
                renderBoard();

                API.patch('/applications/' + encodeURIComponent(id) + '/status?new_status=' + encodeURIComponent(newStatus))
                    .then(() => {
                        // 状态变更成功后，在新列中排序
                        return reorderInColumn(newStatus, id, insertIndex);
                    })
                    .catch((err) => {
                        app.status = oldStatus;
                        renderBoard();
                        API.toast('状态更新失败: ' + err.message, 'error');
                    });
            }
        });
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        root.innerHTML = renderSkeleton();
        bindEvents();
        await loadAll();
    }

    function cleanup() {
        document.removeEventListener('keydown', onModalKeydown);
        if (modalOverlay) {
            modalOverlay.remove();
            modalOverlay = null;
        }
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.kanban = { mount: mount, cleanup: cleanup, title: '投递看板' };
})(window);
