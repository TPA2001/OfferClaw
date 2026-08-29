/**
 * 投递总览视图 — 统计概览 + 跟进提醒（不含看板列）
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const Motion = global.OfferClawMotion;
    const esc = API.esc.bind(API);

    // ============ 状态 ============

    const state = {
        stats: null,
        followups: null,
        applications: [],
        loading: true,
    };

    let root = null;

    // ============ CSS ============

    const CSS_ID = 'overview-styles';

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.ov-view { padding-bottom: 0; height: 100%; display: flex; flex-direction: column; overflow-y: auto; }

/* --- 统计栏 --- */
.ov-stats-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.9rem;
    margin-bottom: 1rem;
    flex-shrink: 0;
}
.ov-stat-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    position: relative;
    overflow: hidden;
    transition: box-shadow 0.25s var(--ease), transform 0.25s var(--ease);
}
.ov-stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--olive);
    transform: scaleX(0.3);
    transform-origin: left;
    transition: transform 0.5s var(--ease-out);
}
.ov-stat-card.accent-info::before { background: var(--info); }
.ov-stat-card.accent-success::before { background: var(--success); }
.ov-stat-card.accent-warn::before { background: var(--warn); }
.ov-stat-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.ov-stat-card:hover::before { transform: scaleX(1); }
.ov-stat-label {
    font-size: 0.76rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
}
.ov-stat-value {
    font-family: var(--font-serif);
    font-size: 1.9rem;
    font-weight: 900;
    color: var(--ink);
    line-height: 1.1;
}
.ov-stat-sub {
    font-size: 0.72rem;
    color: var(--ink-faint);
    margin-top: 0.25rem;
}
.ov-stat-card.accent-info .ov-stat-value { color: color-mix(in srgb, var(--info) 82%, var(--ink)); }
.ov-stat-card.accent-success .ov-stat-value { color: color-mix(in srgb, var(--success) 82%, var(--ink)); }
.ov-stat-card.accent-warn .ov-stat-value { color: color-mix(in srgb, var(--warn) 82%, var(--ink)); }

/* --- 跟进提醒 --- */
.ov-followups {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.9rem;
    margin-bottom: 1rem;
    flex-shrink: 0;
}
.ov-followup-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-left: 3px solid var(--ink-faint);
    border-radius: 8px;
    padding: 0.8rem 0.95rem;
    transition: box-shadow 0.2s var(--ease), border-color 0.2s var(--ease), transform 0.2s var(--ease);
}
.ov-followup-card:hover { box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.ov-followup-card.stale { border-left-color: var(--warn); }
.ov-followup-card.assessment { border-left-color: var(--st-assessment); }
.ov-followup-card.interview { border-left-color: var(--st-interview); }
.ov-followup-card.offer { border-left-color: var(--st-offer); }
.ov-followup-card.stale:not(.empty) { background: linear-gradient(135deg, color-mix(in srgb, var(--warn) 7%, var(--card)), var(--card) 60%); }
.ov-followup-card.assessment:not(.empty) { background: linear-gradient(135deg, color-mix(in srgb, var(--st-assessment) 7%, var(--card)), var(--card) 60%); }
.ov-followup-card.interview:not(.empty) { background: linear-gradient(135deg, color-mix(in srgb, var(--st-interview) 7%, var(--card)), var(--card) 60%); }
.ov-followup-card.offer:not(.empty) { background: linear-gradient(135deg, color-mix(in srgb, var(--st-offer) 8%, var(--card)), var(--card) 60%); }
.ov-followup-card.empty { opacity: 0.55; }
.ov-fu-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
}
.ov-fu-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 0.35rem;
}
.ov-fu-count {
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
.ov-followup-card.stale .ov-fu-count { color: color-mix(in srgb, var(--warn) 72%, var(--ink)); background: color-mix(in srgb, var(--warn) 15%, transparent); }
.ov-followup-card.assessment .ov-fu-count { color: color-mix(in srgb, var(--st-assessment) 72%, var(--ink)); background: color-mix(in srgb, var(--st-assessment) 15%, transparent); }
.ov-followup-card.interview .ov-fu-count { color: color-mix(in srgb, var(--st-interview) 72%, var(--ink)); background: color-mix(in srgb, var(--st-interview) 15%, transparent); }
.ov-followup-card.offer .ov-fu-count { color: color-mix(in srgb, var(--st-offer) 72%, var(--ink)); background: color-mix(in srgb, var(--st-offer) 15%, transparent); }
.ov-followup-card.empty .ov-fu-count { background: var(--paper-deep); color: var(--ink-faint); }
.ov-fu-list { display: flex; flex-direction: column; gap: 0.3rem; }
.ov-fu-item {
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
.ov-fu-item:hover { background: var(--olive-soft); color: var(--olive-dark); }
.ov-fu-item.overdue { color: var(--warn); font-weight: 600; }
.ov-fu-item.unscheduled { opacity: 0.6; }
.ov-fu-empty {
    font-size: 0.74rem;
    color: var(--ink-faint);
    padding: 0.3rem 0;
}
.ov-fu-more {
    font-size: 0.72rem;
    color: var(--ink-faint);
    padding: 0.2rem 0.5rem;
}

@media (max-width: 900px) {
    .ov-stats-bar, .ov-followups { grid-template-columns: repeat(2, 1fr); }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

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

    function fmtHours(h) {
        if (h == null) return '';
        if (h < 0) {
            const a = Math.abs(h);
            if (a < 24) return '逾期 ' + Math.round(a) + ' 小时';
            return '逾期 ' + Math.round(a / 24) + ' 天';
        }
        if (h < 24) return Math.round(h) + '小时后';
        return Math.round(h / 24) + '天后';
    }

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
        <div class="view-container ov-view">
            <div class="view-title-row" style="margin-bottom:1rem;">
                <span class="header-eyebrow">OVERVIEW</span>
                <h1>投递总览</h1>
                <p class="view-subtitle">求职投递数据概览与跟进提醒</p>
            </div>
            <div id="ov-stats"></div>
            <div id="ov-followups"></div>
        </div>`;
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
        <div class="ov-stats-bar">
            <div class="ov-stat-card">
                <div class="ov-stat-label">投递总数</div>
                <div class="ov-stat-value" data-target="${total}">0</div>
                <div class="ov-stat-sub">共 ${total} 条记录</div>
            </div>
            <div class="ov-stat-card accent-info">
                <div class="ov-stat-label">回复率</div>
                <div class="ov-stat-value" data-target="${replyRate}" data-decimals="${rateDecimals(replyStr)}" data-suffix="%">0%</div>
                <div class="ov-stat-sub">已投递中获得回复</div>
            </div>
            <div class="ov-stat-card accent-success">
                <div class="ov-stat-label">Offer 率</div>
                <div class="ov-stat-value" data-target="${offerRate}" data-decimals="${rateDecimals(offerStr)}" data-suffix="%">0%</div>
                <div class="ov-stat-sub">${offerCount} 个 offer</div>
            </div>
            <div class="ov-stat-card accent-warn">
                <div class="ov-stat-label">停滞投递</div>
                <div class="ov-stat-value" data-target="${stale}">0</div>
                <div class="ov-stat-sub">超过 7 天未回复</div>
            </div>
        </div>`;
    }

    function animateStats() {
        const els = root.querySelectorAll('.ov-stat-value');
        els.forEach(el => {
            const target = parseFloat(el.dataset.target || '0');
            const decimals = el.dataset.decimals ? parseInt(el.dataset.decimals, 10) : 0;
            const suffix = el.dataset.suffix || '';
            Motion.countUp(el, target, { duration: 900, decimals: decimals, suffix: suffix });
        });
    }

    function renderFollowups() {
        const fu = normalizeFollowups(state.followups);
        const timeCls = a => a.hours_until == null ? 'unscheduled' : (a.hours_until < 0 ? 'overdue' : '');
        const cards = [
            {
                cls: 'stale', title: '停滞投递', icon: '⏰',
                items: fu.stale,
                render: a => `${esc(a.company)} · ${esc(a.position)} — 等待${a.stale_days || 0}天`,
            },
            {
                cls: 'assessment', title: '待完成笔试', icon: '✍',
                items: fu.assessments,
                render: a => `${esc(a.company)} · ${esc(a.position)} — ${a.hours_until == null ? '未设置截止时间' : esc(fmtHours(a.hours_until))}`,
                itemCls: timeCls,
            },
            {
                cls: 'interview', title: '即将面试', icon: '🎤',
                items: fu.interviews,
                render: a => `${esc(a.company)} · ${esc(a.position)} — ${a.hours_until == null ? '未安排时间' : esc(fmtHours(a.hours_until))}`,
                itemCls: timeCls,
            },
            {
                cls: 'offer', title: '待回复 Offer', icon: '🎉',
                items: fu.offers,
                render: a => `${esc(a.company)} · ${esc(a.position)}${pick(a, 'offer_salary', 'salary_range') ? ' — ' + esc(pick(a, 'offer_salary', 'salary_range')) : ''}`,
            },
        ];

        return `<div class="ov-followups">${cards.map(c => {
            const empty = c.items.length === 0;
            let list;
            if (empty) {
                list = '<div class="ov-fu-empty">暂无提醒</div>';
            } else {
                list = c.items.slice(0, 4).map(a => {
                    const extra = c.itemCls ? c.itemCls(a) : '';
                    return `<div class="ov-fu-item ${extra}" data-id="${esc(a.id)}" title="点击编辑">${c.render(a)}</div>`;
                }).join('');
                if (c.items.length > 4) {
                    list += `<div class="ov-fu-more">还有 ${c.items.length - 4} 项，前往投递看板查看</div>`;
                }
            }
            return `
                <div class="ov-followup-card ${c.cls} ${empty ? 'empty' : ''}">
                    <div class="ov-fu-head">
                        <span class="ov-fu-title">${c.icon} ${c.title}</span>
                        <span class="ov-fu-count">${c.items.length}</span>
                    </div>
                    <div class="ov-fu-list">${list}</div>
                </div>`;
        }).join('')}</div>`;
    }

    function pick(obj) {
        if (!obj) return null;
        for (let i = 1; i < arguments.length; i++) {
            const v = obj[arguments[i]];
            if (v !== null && v !== undefined && v !== '') return v;
        }
        return null;
    }

    // ============ 数据加载 ============

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

    async function loadAll() {
        state.loading = true;
        await Promise.all([loadStats(), loadFollowups()]);
        state.loading = false;
        renderTopSections();
    }

    function renderTopSections() {
        const statsEl = root.querySelector('#ov-stats');
        const fuEl = root.querySelector('#ov-followups');
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
        const fuEl = root.querySelector('#ov-followups');
        if (!fuEl) return;
        fuEl.querySelectorAll('.ov-fu-item').forEach(item => {
            item.addEventListener('click', () => {
                // 点击提醒项跳转到投递看板
                global.OfferClawRouter.navigate('/kanban');
            });
        });
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        root.innerHTML = renderSkeleton();
        await loadAll();
    }

    function cleanup() {
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.overview = { mount: mount, cleanup: cleanup, title: '投递总览' };
})(window);
