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

    // ============ 状态 ============

    const state = {
        applications: [],
        stats: null,
        followups: null,
        filters: { search: '', source: '', priority: '' },
        editing: null,   // null=新建, 对象=编辑
        loading: true,
    };

    let root = null;
    let modalOverlay = null;
    let draggedId = null;

    // ============ CSS ============

    const CSS_ID = 'kanban-styles';

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.kb-view { padding-bottom: 4rem; }

/* --- 统计栏 --- */
.kb-stats-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.9rem;
    margin-bottom: 1.4rem;
}
.kb-stat-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    position: relative;
    overflow: hidden;
    transition: box-shadow 0.25s var(--ease), transform 0.25s var(--ease);
}
.kb-stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--olive);
    transform: scaleX(0.3);
    transform-origin: left;
    transition: transform 0.5s var(--ease-out);
}
.kb-stat-card.accent-olive::before { background: var(--olive); }
.kb-stat-card.accent-terra::before { background: var(--terra); }
.kb-stat-card.accent-warn::before { background: var(--warn); }
.kb-stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.kb-stat-card:hover::before { transform: scaleX(1); }
.kb-stat-label {
    font-size: 0.76rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
}
.kb-stat-value {
    font-family: var(--font-serif);
    font-size: 1.9rem;
    font-weight: 900;
    color: var(--ink);
    line-height: 1.1;
}
.kb-stat-sub {
    font-size: 0.72rem;
    color: var(--ink-faint);
    margin-top: 0.25rem;
}

/* --- 跟进提醒 --- */
.kb-followups {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.9rem;
    margin-bottom: 1.4rem;
}
.kb-followup-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-left: 3px solid var(--ink-faint);
    border-radius: 8px;
    padding: 0.8rem 0.95rem;
    transition: box-shadow 0.2s var(--ease);
}
.kb-followup-card:hover { box-shadow: var(--shadow-sm); }
.kb-followup-card.stale { border-left-color: var(--warn); }
.kb-followup-card.assessment { border-left-color: var(--st-assessment); }
.kb-followup-card.interview { border-left-color: var(--st-interview); }
.kb-followup-card.offer { border-left-color: var(--st-offer); }
.kb-followup-card.empty { opacity: 0.55; }
.kb-fu-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
}
.kb-fu-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 0.35rem;
}
.kb-fu-count {
    font-family: var(--font-mono);
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--olive-dark);
    background: var(--olive-soft);
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    min-width: 24px;
    text-align: center;
}
.kb-followup-card.empty .kb-fu-count { background: var(--paper-deep); color: var(--ink-faint); }
.kb-fu-list { display: flex; flex-direction: column; gap: 0.3rem; }
.kb-fu-item {
    font-size: 0.76rem;
    color: var(--ink-soft);
    padding: 0.35rem 0.5rem;
    border-radius: 5px;
    cursor: pointer;
    transition: background 0.15s var(--ease);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.kb-fu-item:hover { background: var(--olive-soft); color: var(--olive-dark); }
.kb-fu-empty {
    font-size: 0.76rem;
    color: var(--ink-faint);
    padding: 0.35rem 0.5rem;
    font-style: italic;
}

/* --- 筛选栏 --- */
.kb-filter-bar {
    display: flex;
    gap: 0.6rem;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 1.2rem;
    padding: 0.7rem 0.9rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
}
.kb-search-input {
    flex: 1;
    min-width: 180px;
    padding: 0.45rem 0.75rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.85rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.kb-search-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: #fff;
}
.kb-filter-select {
    padding: 0.45rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.82rem;
    font-family: inherit;
    cursor: pointer;
}
.kb-filter-select:focus { outline: none; border-color: var(--olive); }
.kb-filter-actions { display: flex; gap: 0.4rem; margin-left: auto; }

/* --- 看板 --- */
.kb-board {
    display: flex;
    gap: 0.7rem;
    overflow-x: auto;
    padding-bottom: 0.6rem;
    min-height: 380px;
}
.kb-column {
    flex: 0 0 280px;
    background: var(--paper-light);
    border: 1px solid var(--line);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    max-height: 70vh;
}
.kb-column-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.65rem 0.85rem;
    border-top: 3px solid var(--col-color, var(--olive));
    border-bottom: 1px solid var(--line-soft);
    background: var(--card);
    border-radius: 7px 7px 0 0;
}
.kb-column-title {
    font-family: var(--font-serif);
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--ink);
}
.kb-column-count {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--ink-soft);
    background: var(--paper-deep);
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
    min-width: 22px;
    text-align: center;
}
.kb-column-body {
    flex: 1;
    overflow-y: auto;
    padding: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    transition: background 0.18s var(--ease);
}
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

/* --- 卡片 --- */
.app-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 0.7rem 0.8rem;
    cursor: grab;
    transition: box-shadow 0.2s var(--ease), transform 0.2s var(--ease), border-color 0.2s var(--ease);
    position: relative;
}
.app-card:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--olive);
    transform: translateY(-1px);
}
.app-card:active { cursor: grabbing; }
.app-card.card-dragging { opacity: 0.4; transform: rotate(2deg); }
.app-card.priority-high { border-left: 3px solid var(--terra); }
.app-card.priority-low { border-left: 3px solid var(--line); }
.card-top-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
    margin-bottom: 0.2rem;
}
.card-company {
    font-family: var(--font-serif);
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 75%;
}
.card-priority {
    font-size: 0.66rem;
    font-weight: 700;
    padding: 0.1rem 0.4rem;
    border-radius: 8px;
    flex-shrink: 0;
    line-height: 1.4;
}
.card-priority.priority-high { background: var(--terra-soft); color: var(--terra-deep); }
.card-priority.priority-medium { background: var(--olive-soft); color: var(--olive-dark); }
.card-priority.priority-low { background: var(--paper-deep); color: var(--ink-faint); }
.card-position {
    font-size: 0.8rem;
    color: var(--ink-soft);
    margin-bottom: 0.4rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.card-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.74rem;
    color: var(--ink-faint);
    margin-bottom: 0.35rem;
}
.card-salary { color: var(--terra-deep); font-weight: 600; }
.card-countdown {
    font-size: 0.72rem;
    padding: 0.25rem 0.5rem;
    border-radius: 5px;
    background: var(--olive-soft);
    color: var(--olive-dark);
    margin-bottom: 0.4rem;
    font-weight: 500;
}
.card-countdown.urgent {
    background: var(--terra-soft);
    color: var(--terra-deep);
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
    background: #fff;
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
    .kb-stats-bar, .kb-followups { grid-template-columns: repeat(2, 1fr); }
    .kb-form-grid, .kb-field-group { grid-template-columns: 1fr; }
    .kb-column { flex: 0 0 240px; }
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

    function parseRate(v) {
        if (v == null) return 0;
        if (typeof v === 'number') return v;
        const n = parseFloat(String(v).replace('%', '').trim());
        return isNaN(n) ? 0 : n;
    }

    function rateDecimals(v) {
        if (typeof v === 'string' && v.indexOf('.') >= 0) return 1;
        return 0;
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

    function fmtHours(h) {
        if (h == null) return '';
        if (h < 24) return Math.round(h) + '小时后';
        return Math.round(h / 24) + '天后';
    }

    /** 规范化跟进提醒结构（兼容两种字段命名） */
    function normalizeFollowups(f) {
        if (!f) return { stale: [], assessments: [], interviews: [], offers: [] };
        return {
            stale: f.stale || [],
            assessments: f.assessments || f.pending_assessments || [],
            interviews: f.interviews || f.upcoming_interviews || [],
            offers: f.offers || f.pending_offers || [],
        };
    }

    // ============ 渲染 ============

    function renderSkeleton() {
        return `
        <div class="view-container kb-view">
            <div class="view-header">
                <div class="header-eyebrow">DASHBOARD</div>
                <h1>投递看板</h1>
                <p>追踪所有求职投递的状态与进度</p>
            </div>
            <div id="kb-stats"></div>
            <div id="kb-followups"></div>
            <div class="kb-filter-bar">
                <input type="text" id="kb-search" class="kb-search-input" placeholder="搜索公司或职位...">
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
                    <button class="btn btn-ghost btn-sm" id="kb-import-btn">导入</button>
                    <button class="btn btn-ghost btn-sm" id="kb-export-btn">导出</button>
                    <button class="btn btn-primary btn-sm" id="kb-create-btn">+ 新建投递</button>
                    <input type="file" id="kb-import-input" accept=".json,application/json" style="display:none">
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

    function renderStatsBar() {
        const s = state.stats || {};
        const total = s.total || 0;
        const replyStr = s.reply_rate || '0';
        const offerStr = s.offer_rate || '0';
        const stale = s.stale_count || 0;
        const replyRate = parseRate(replyStr);
        const offerRate = parseRate(offerStr);
        const offerCount = s.offer_count != null ? s.offer_count :
            ((s.by_status && (s.by_status['已录用'] || s.by_status['offer'])) || 0);

        return `
        <div class="kb-stats-bar">
            <div class="kb-stat-card">
                <div class="kb-stat-label">投递总数</div>
                <div class="kb-stat-value" data-target="${total}">0</div>
                <div class="kb-stat-sub">共 ${total} 条记录</div>
            </div>
            <div class="kb-stat-card accent-olive">
                <div class="kb-stat-label">回复率</div>
                <div class="kb-stat-value" data-target="${replyRate}" data-decimals="${rateDecimals(replyStr)}" data-suffix="%">0%</div>
                <div class="kb-stat-sub">已投递中获得回复</div>
            </div>
            <div class="kb-stat-card accent-terra">
                <div class="kb-stat-label">Offer 率</div>
                <div class="kb-stat-value" data-target="${offerRate}" data-decimals="${rateDecimals(offerStr)}" data-suffix="%">0%</div>
                <div class="kb-stat-sub">${offerCount} 个 offer</div>
            </div>
            <div class="kb-stat-card accent-warn">
                <div class="kb-stat-label">停滞投递</div>
                <div class="kb-stat-value" data-target="${stale}">0</div>
                <div class="kb-stat-sub">超过 7 天未回复</div>
            </div>
        </div>`;
    }

    function animateStats() {
        const els = root.querySelectorAll('.kb-stat-value');
        els.forEach(el => {
            const target = parseFloat(el.dataset.target || '0');
            const decimals = el.dataset.decimals ? parseInt(el.dataset.decimals, 10) : 0;
            const suffix = el.dataset.suffix || '';
            Motion.countUp(el, target, { duration: 900, decimals: decimals, suffix: suffix });
        });
    }

    function renderFollowups() {
        const fu = normalizeFollowups(state.followups);
        const cards = [
            {
                cls: 'stale', title: '停滞投递', icon: '⏰',
                items: fu.stale,
                render: a => `${esc(a.company)} · ${esc(a.position)} — 等待${a.stale_days || 0}天`,
            },
            {
                cls: 'assessment', title: '待完成笔试', icon: '✍',
                items: fu.assessments,
                render: a => `${esc(a.company)} · ${esc(a.position)} — ${esc(fmtHours(a.hours_until))}`,
            },
            {
                cls: 'interview', title: '即将面试', icon: '🎤',
                items: fu.interviews,
                render: a => `${esc(a.company)} · ${esc(a.position)} — ${esc(fmtHours(a.hours_until))}`,
            },
            {
                cls: 'offer', title: '待回复 Offer', icon: '🎉',
                items: fu.offers,
                render: a => `${esc(a.company)} · ${esc(a.position)}${pick(a, 'offer_salary', 'salary_range') ? ' — ' + esc(pick(a, 'offer_salary', 'salary_range')) : ''}`,
            },
        ];

        return `<div class="kb-followups">${cards.map(c => {
            const empty = c.items.length === 0;
            const list = empty
                ? '<div class="kb-fu-empty">暂无提醒</div>'
                : c.items.slice(0, 4).map(a =>
                    `<div class="kb-fu-item" data-id="${esc(a.id)}" title="点击编辑">${c.render(a)}</div>`
                ).join('');
            return `
                <div class="kb-followup-card ${c.cls} ${empty ? 'empty' : ''}">
                    <div class="kb-fu-head">
                        <span class="kb-fu-title">${c.icon} ${c.title}</span>
                        <span class="kb-fu-count">${c.items.length}</span>
                    </div>
                    <div class="kb-fu-list">${list}</div>
                </div>`;
        }).join('')}</div>`;
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

        board.innerHTML = STATUSES.map(s => renderColumn(s, grouped[s.key])).join('');
    }

    function renderColumn(s, apps) {
        const cards = apps.map(renderCard).join('');
        return `
        <div class="kb-column" data-status="${s.key}">
            <div class="kb-column-header" style="--col-color:${s.color}">
                <span class="kb-column-title">${s.label}</span>
                <span class="kb-column-count">${apps.length}</span>
            </div>
            <div class="kb-column-body" data-status="${s.key}">
                ${cards || '<div class="kb-col-empty">拖拽卡片到此列</div>'}
            </div>
        </div>`;
    }

    function renderCard(app) {
        const priority = pick(app, 'priority') || 'medium';
        const priorityLabel = PRIORITY_LABELS[priority] || priority;
        const salary = pick(app, 'salary_range', 'offer_salary');
        const dateText = formatDaysWaiting(pick(app, 'applied_at'));

        // 倒计时（按状态显示相关字段）
        const countdowns = [];
        if (app.status === 'assessment') {
            const dl = pick(app, 'assessment_deadline');
            if (dl) countdowns.push({ label: '笔试', ts: dl });
        }
        if (app.status === 'interview') {
            const it = pick(app, 'interview_time', 'next_interview_at');
            if (it) countdowns.push({ label: '面试', ts: it });
        }
        if (app.status === 'offer') {
            const od = pick(app, 'offer_deadline');
            if (od) countdowns.push({ label: 'Offer', ts: od });
        }

        const cdHtml = countdowns.map(c => {
            const cd = formatCountdown(c.ts);
            const cls = cd.urgent ? 'card-countdown urgent' : 'card-countdown';
            return `<div class="${cls}">${esc(c.label)}: ${esc(cd.text)}</div>`;
        }).join('');

        const canAdvance = PIPELINE.indexOf(app.status) >= 0 && PIPELINE.indexOf(app.status) < PIPELINE.length - 1;

        return `
        <div class="app-card priority-${priority}" draggable="true" data-id="${esc(app.id)}">
            <div class="card-top-row">
                <span class="card-company" title="${esc(app.company)}">${esc(app.company || '未知公司')}</span>
                <span class="card-priority priority-${priority}">${esc(priorityLabel)}</span>
            </div>
            <div class="card-position" title="${esc(app.position)}">${esc(app.position || '未知职位')}</div>
            <div class="card-meta">
                ${salary ? `<span class="card-salary">${esc(salary)}</span>` : '<span></span>'}
                <span class="card-date">${esc(dateText)}</span>
            </div>
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
        const status = a.status || 'applied';
        const priority = a.priority || 'medium';
        const sources = Array.from(new Set(state.applications.map(x => x.source).filter(Boolean))).sort();

        const roundLabels = ['', '一面', '二面', '三面', 'HR面', '加面'];
        const interviewRound = pick(a, 'interview_round');
        const interviewFormat = pick(a, 'interview_format');
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
                                    <label>笔试类型</label>
                                    <input name="assessment_type" value="${esc(a.assessment_type || '')}" placeholder="如 在线编程 / 行测">
                                </div>
                                <div class="kb-field">
                                    <label>笔试截止</label>
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
                                <div class="kb-field full">
                                    <label>面试形式</label>
                                    <select name="interview_format">
                                        <option value="">未选择</option>
                                        ${['现场', '视频', '电话'].map(f => `<option ${interviewFormat === f ? 'selected' : ''}>${f}</option>`).join('')}
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

    function openCreateModal() {
        state.editing = null;
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
    }

    function collectFormData() {
        const form = modalOverlay.querySelector('#kb-form');
        const fd = new FormData(form);
        const data = {};
        const datetimeFields = ['applied_at', 'assessment_deadline', 'interview_time', 'offer_deadline'];

        for (const [k, v] of fd.entries()) {
            if (datetimeFields.indexOf(k) >= 0) {
                const iso = fromLocalInput(v);
                if (iso) data[k] = iso;
            } else if (k === 'interview_round') {
                if (v !== '') data[k] = parseInt(v, 10);
            } else {
                if (v !== '') data[k] = v;
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
            // 后台刷新统计与跟进
            loadStats();
            loadFollowups();
        } catch (e) {
            // 回滚
            app.status = oldStatus;
            renderBoard();
            API.toast('状态更新失败: ' + e.message, 'error');
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

    async function loadStats() {
        try {
            state.stats = await API.get('/applications/stats/overview');
        } catch (e) {
            state.stats = state.stats || null;
        }
    }

    async function loadFollowups() {
        try {
            state.followups = await API.get('/applications/stats/followups');
        } catch (e) {
            state.followups = null;
        }
    }

    function renderTopSections() {
        const statsEl = root.querySelector('#kb-stats');
        const fuEl = root.querySelector('#kb-followups');
        if (statsEl) {
            statsEl.innerHTML = renderStatsBar();
            animateStats();
        }
        if (fuEl) {
            fuEl.innerHTML = renderFollowups();
            bindFollowupEvents();
        }
    }

    function bindFollowupEvents() {
        const fuEl = root.querySelector('#kb-followups');
        if (!fuEl) return;
        fuEl.querySelectorAll('.kb-fu-item').forEach(item => {
            item.addEventListener('click', () => {
                const id = item.dataset.id;
                const app = state.applications.find(a => a.id === id);
                if (app) openEditModal(app);
            });
        });
    }

    async function loadAll() {
        state.loading = true;
        renderBoard();
        await Promise.all([loadApplications(), loadStats(), loadFollowups()]);
        state.loading = false;
        updateSourceFilter();
        renderTopSections();
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

        // 拖拽
        board.addEventListener('dragstart', (e) => {
            const card = e.target.closest('.app-card');
            if (!card) return;
            draggedId = card.dataset.id;
            card.classList.add('card-dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', draggedId); } catch (_) {}
        });

        board.addEventListener('dragend', (e) => {
            const card = e.target.closest('.app-card');
            if (card) card.classList.remove('card-dragging');
            draggedId = null;
            board.querySelectorAll('.kb-drag-over').forEach(el => el.classList.remove('kb-drag-over'));
        });

        board.addEventListener('dragover', (e) => {
            const col = e.target.closest('.kb-column-body');
            if (!col) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
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
            const id = draggedId || (function () {
                try { return e.dataTransfer.getData('text/plain'); } catch (_) { return ''; }
            })();
            const newStatus = col.dataset.status;
            if (id && newStatus) changeStatus(id, newStatus);
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
