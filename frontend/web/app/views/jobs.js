/**
 * 岗位搜索视图 — Boss 直聘搜索 + 我的岗位列表
 * 登录态横幅 + 搜索栏（关键字/城市）+ 岗位卡片 + 分页 + 已保存岗位 Tab
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const Motion = global.OfferClawMotion;
    const Router = global.OfferClawRouter;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const CITIES = [
        '', '北京', '上海', '深圳', '广州', '杭州', '成都', '南京',
        '武汉', '西安', '苏州', '天津', '重庆', '厦门', '长沙', '青岛',
    ];

    const STATUS_LABELS = {
        'applied': '已投递',
        'assessment': '笔试中',
        'interview': '面试中',
        'offer': '已录用',
        'rejected': '已拒绝',
        'withdrawn': '已撤回',
    };

    const CSS_ID = 'jobs-styles';

    // ============ 状态 ============

    const state = {
        tab: 'boss',                 // 'boss' | 'mine'
        login: { logged_in: false, anti_crawl: false, checked: false },
        search: { keyword: '', city: '', page: 1 },
        results: { jobs: [], source: '', need_login: false, anti_crawl: false },
        mineApps: [],
        savedIds: new Set(),         // 已加入看板的 job_url 集合，用于禁用重复保存
        loadingLogin: false,
        loadingSearch: false,
        loadingMine: false,
    };

    let root = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.jobs-view { padding-bottom: 4rem; }

/* --- 登录横幅 --- */
.login-banner {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 0.75rem 1rem;
    border-radius: 10px;
    margin-bottom: 1.2rem;
    border: 1px solid var(--line);
    background: var(--card);
    transition: border-color 0.25s var(--ease), background 0.25s var(--ease);
}
.login-banner.ok { border-color: var(--olive); background: var(--olive-soft); }
.login-banner.warn { border-color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, var(--card)); }
.login-banner.err { border-color: var(--danger); background: var(--terra-soft); }
.login-banner-icon {
    width: 34px; height: 34px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.05rem; font-weight: 700;
    flex-shrink: 0;
}
.login-banner.ok .login-banner-icon { background: var(--olive); color: var(--paper-light); }
.login-banner.warn .login-banner-icon { background: var(--warn); color: var(--paper-light); }
.login-banner.err .login-banner-icon { background: var(--danger); color: var(--paper-light); }
.login-banner-text { flex: 1; min-width: 0; }
.login-banner-title {
    font-size: 0.86rem; font-weight: 600; color: var(--ink);
    margin-bottom: 0.1rem;
}
.login-banner-desc {
    font-size: 0.76rem; color: var(--ink-soft);
}
.login-banner .btn { flex-shrink: 0; }

/* --- Tabs --- */
.jobs-tabs {
    display: flex;
    gap: 0.2rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--line);
}

/* --- 搜索栏 --- */
.search-bar {
    display: flex;
    gap: 0.6rem;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 1rem;
    padding: 0.8rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
}
.search-bar .jobs-keyword {
    flex: 1;
    min-width: 200px;
    padding: 0.5rem 0.8rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.9rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.search-bar .jobs-keyword:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: var(--card);
}
.search-bar .jobs-city {
    padding: 0.5rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.85rem;
    font-family: inherit;
    cursor: pointer;
    min-width: 100px;
}
.search-bar .jobs-city:focus { outline: none; border-color: var(--olive); }

/* --- 来源徽标 --- */
.source-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.72rem;
    font-family: var(--font-mono);
    padding: 0.2rem 0.55rem;
    border-radius: 10px;
    font-weight: 600;
}
.source-badge.real { background: var(--olive-soft); color: var(--olive-dark); }
.source-badge.mock { background: var(--paper-deep); color: var(--ink-faint); }
.source-badge::before {
    content: '';
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
}

/* --- 岗位列表 --- */
.jobs-list {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
}
.job-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    transition: box-shadow 0.2s var(--ease), transform 0.2s var(--ease), border-color 0.2s var(--ease);
    position: relative;
}
.job-card:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--olive);
    transform: translateY(-1px);
}
.job-card.saved { border-left: 3px solid var(--olive); }
.job-card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 0.4rem;
}
.job-title {
    font-family: var(--font-serif);
    font-size: 1rem;
    font-weight: 700;
    color: var(--ink);
    line-height: 1.3;
}
.job-salary {
    font-family: var(--font-mono);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--terra-deep);
    white-space: nowrap;
    flex-shrink: 0;
}
.job-company {
    font-size: 0.86rem;
    color: var(--olive-dark);
    font-weight: 600;
    margin-bottom: 0.5rem;
}
.job-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 0.9rem;
    font-size: 0.78rem;
    color: var(--ink-soft);
    margin-bottom: 0.5rem;
}
.job-meta-item {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
}
.job-hr {
    font-size: 0.78rem;
    color: var(--ink-faint);
    padding: 0.35rem 0.6rem;
    background: var(--paper-light);
    border-radius: 6px;
    margin-bottom: 0.6rem;
    display: inline-block;
}
.job-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-bottom: 0.7rem;
}
.job-tag {
    font-size: 0.7rem;
    padding: 0.15rem 0.5rem;
    background: var(--paper-deep);
    color: var(--ink-soft);
    border-radius: 4px;
}
.job-actions {
    display: flex;
    gap: 0.5rem;
    padding-top: 0.6rem;
    border-top: 1px dashed var(--line-soft);
}
.job-actions .btn { flex: 0 0 auto; }
.job-actions .job-link {
    margin-left: auto;
    align-self: center;
    font-size: 0.8rem;
    color: var(--olive);
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
}
.job-actions .job-link:hover { text-decoration: underline; color: var(--olive-dark); }

/* --- 分页 --- */
.jobs-pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.8rem;
    margin-top: 1.4rem;
}
.jobs-page-info {
    font-size: 0.82rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
}

/* --- 我的岗位列表 --- */
.mine-list {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
}
.mine-item {
    background: var(--card);
    border: 1px solid var(--line);
    border-left: 3px solid var(--olive);
    border-radius: 8px;
    padding: 0.8rem 1rem;
    display: flex;
    align-items: center;
    gap: 0.9rem;
    transition: box-shadow 0.2s var(--ease), transform 0.2s var(--ease);
}
.mine-item:hover { box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.mine-item.st-applied { border-left-color: var(--st-applied); }
.mine-item.st-assessment { border-left-color: var(--st-assessment); }
.mine-item.st-interview { border-left-color: var(--st-interview); }
.mine-item.st-offer { border-left-color: var(--st-offer); }
.mine-item.st-rejected { border-left-color: var(--st-rejected); }
.mine-item.st-withdrawn { border-left-color: var(--st-withdrawn); }
.mine-main { flex: 1; min-width: 0; }
.mine-row1 {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.2rem;
}
.mine-company {
    font-family: var(--font-serif);
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--ink);
}
.mine-status {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.12rem 0.5rem;
    border-radius: 8px;
    background: var(--olive-soft);
    color: var(--olive-dark);
}
/* 状态徽章按状态着色，与看板色板一致 */
.mine-status.st-applied { background: var(--st-applied-soft); color: var(--st-applied-deep); }
.mine-status.st-assessment { background: var(--st-assessment-soft); color: var(--st-assessment-deep); }
.mine-status.st-interview { background: var(--st-interview-soft); color: var(--st-interview-deep); }
.mine-status.st-offer { background: var(--st-offer-soft); color: var(--st-offer-deep); }
.mine-status.st-rejected { background: var(--st-rejected-soft); color: var(--st-rejected-deep); }
.mine-status.st-withdrawn { background: var(--st-withdrawn-soft); color: var(--st-withdrawn-deep); }
.mine-position {
    font-size: 0.82rem;
    color: var(--ink-soft);
}
.mine-meta {
    font-size: 0.74rem;
    color: var(--ink-faint);
    margin-top: 0.2rem;
    display: flex;
    gap: 0.8rem;
    flex-wrap: wrap;
}

/* --- 加载/空态 --- */
.jobs-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.8rem;
    padding: 2.5rem 1rem;
    color: var(--ink-faint);
    font-size: 0.86rem;
}

@media (max-width: 700px) {
    .search-bar { flex-direction: column; align-items: stretch; }
    .search-bar .jobs-keyword, .search-bar .jobs-city { width: 100%; }
    .job-card-head { flex-direction: column; gap: 0.3rem; }
    .mine-item { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function pick(obj) {
        if (!obj) return null;
        for (let i = 1; i < arguments.length; i++) {
            const v = obj[arguments[i]];
            if (v !== null && v !== undefined && v !== '') return v;
        }
        return null;
    }

    function formatRelative(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        const diff = Date.now() - d.getTime();
        if (diff < 0) return '未来';
        if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
        if (diff < 604800000) return Math.floor(diff / 86400000) + '天前';
        return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    }

    /** 投递/更新时间：显示具体日期（当年省略年份），1 天内附加相对时间；悬浮提示完整时间 */
    function formatAppliedMeta(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        if (isNaN(d.getTime())) return '';
        const pad = n => String(n).padStart(2, '0');
        const now = new Date();
        const md = pad(d.getMonth() + 1) + '-' + pad(d.getDate());
        const sameYear = d.getFullYear() === now.getFullYear();
        const datePart = sameYear ? md : String(d.getFullYear()).slice(2) + '-' + md;
        const diff = Date.now() - d.getTime();
        const rel = (diff >= 0 && diff < 86400000) ? ' · ' + formatRelative(ts) : '';
        return {
            short: datePart + rel,
            full: d.getFullYear() + '-' + md + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()),
        };
    }

    /** 规范化 Boss 搜索结果（兼容不同字段命名） */
    function normalizeJobs(jobs) {
        if (!Array.isArray(jobs)) return [];
        return jobs.map(j => ({
            title: pick(j, 'title', 'job_name', 'position') || '',
            company: pick(j, 'company', 'company_name', 'brandName') || '',
            salary: pick(j, 'salary', 'salary_desc') || '',
            city: pick(j, 'city', 'area') || '',
            experience: pick(j, 'experience', 'exp') || '',
            education: pick(j, 'education', 'degree') || '',
            job_scale: pick(j, 'job_scale', 'scale') || '',
            hr_name: pick(j, 'hr_name', 'boss_name', 'active_time_desc') || '',
            hr_position: pick(j, 'hr_position', 'boss_title') || '',
            job_url: pick(j, 'job_url', 'url', 'link', 'job_href') || '',
            company_size: pick(j, 'company_size', 'scale') || '',
            stage: pick(j, 'stage', 'finance_stage') || '',
            industry: pick(j, 'industry', 'industry_field') || '',
        }));
    }

    // ============ 渲染 ============

    function renderSkeleton() {
        return `
        <div class="view-container jobs-view">
            <div class="view-header">
                <div class="header-eyebrow">DISCOVER</div>
                <h1>岗位搜索</h1>
                <p>搜索 Boss 直聘岗位，一键加入投递看板</p>
            </div>
            <div id="jobs-login-banner"></div>
            <div class="jobs-tabs">
                <button class="tab active" data-tab="boss">Boss 搜索</button>
                <button class="tab" data-tab="mine">我的岗位</button>
            </div>
            <div id="jobs-tab-content"></div>
        </div>`;
    }

    function renderLoginBanner() {
        const L = state.login;
        const checking = state.loadingLogin;
        let cls, icon, title, desc, btnText, showBtn;

        if (checking && !L.checked) {
            cls = ''; icon = '··'; title = '正在检查登录状态...'; desc = '请稍候'; btnText = ''; showBtn = false;
        } else if (L.anti_crawl) {
            cls = 'err'; icon = '!'; title = '检测到反爬限制';
            desc = 'Boss 直聘触发了滑块验证，已降级为模拟数据。建议稍后重试或手动登录。';
            btnText = '重新登录'; showBtn = true;
        } else if (L.logged_in) {
            cls = 'ok'; icon = '✓'; title = 'Boss 直聘已登录';
            desc = '可获取真实岗位数据'; btnText = ''; showBtn = false;
        } else {
            cls = 'warn'; icon = '!'; title = 'Boss 直聘未登录';
            desc = '登录后可获取真实岗位数据，未登录将使用模拟数据'; btnText = '前往登录'; showBtn = true;
        }

        return `
        <div class="login-banner ${cls}">
            <div class="login-banner-icon">${icon}</div>
            <div class="login-banner-text">
                <div class="login-banner-title">${esc(title)}</div>
                <div class="login-banner-desc">${esc(desc)}</div>
            </div>
            ${showBtn ? `<button class="btn btn-primary btn-sm" id="jobs-open-login">${esc(btnText)}</button>` : ''}
        </div>`;
    }

    function renderSearchBar() {
        const s = state.search;
        return `
        <div class="search-bar">
            <input type="text" class="jobs-keyword" id="jobs-keyword"
                placeholder="搜索职位关键字，如 后端工程师 / 前端 / 产品经理..."
                value="${esc(s.keyword)}">
            <select class="jobs-city" id="jobs-city">
                ${CITIES.map(c => `<option value="${esc(c)}" ${c === s.city ? 'selected' : ''}>${c || '全国'}</option>`).join('')}
            </select>
            <button class="btn btn-primary" id="jobs-search-btn" ${state.loadingSearch ? 'disabled' : ''}>
                ${state.loadingSearch ? '搜索中...' : '搜索'}
            </button>
        </div>`;
    }

    function renderJobCard(job, index) {
        const url = job.job_url || '';
        const saved = url && state.savedIds.has(url);
        const metaItems = [];
        if (job.city) metaItems.push(`<span class="job-meta-item">📍 ${esc(job.city)}</span>`);
        if (job.experience) metaItems.push(`<span class="job-meta-item">💼 ${esc(job.experience)}</span>`);
        if (job.education) metaItems.push(`<span class="job-meta-item">🎓 ${esc(job.education)}</span>`);
        if (job.job_scale) metaItems.push(`<span class="job-meta-item">👥 ${esc(job.job_scale)}</span>`);

        const tags = [];
        if (job.company_size) tags.push(job.company_size);
        if (job.stage) tags.push(job.stage);
        if (job.industry) tags.push(job.industry);

        const hrText = (job.hr_name || job.hr_position)
            ? `HR: ${esc(job.hr_name || '')}${job.hr_position ? ' · ' + esc(job.hr_position) : ''}`
            : '';

        return `
        <div class="job-card ${saved ? 'saved' : ''}" data-idx="${index}">
            <div class="job-card-head">
                <div class="job-title">${esc(job.title || '未知职位')}</div>
                <div class="job-salary">${esc(job.salary || '薪资面议')}</div>
            </div>
            <div class="job-company">${esc(job.company || '未知公司')}</div>
            <div class="job-meta">${metaItems.join('')}</div>
            ${hrText ? `<div class="job-hr">${hrText}</div>` : ''}
            ${tags.length ? `<div class="job-tags">${tags.map(t => `<span class="job-tag">${esc(t)}</span>`).join('')}</div>` : ''}
            <div class="job-actions">
                <button class="btn ${saved ? 'btn-ghost' : 'btn-primary'} btn-sm" data-action="save" ${saved ? 'disabled' : ''}>
                    ${saved ? '已加入看板' : '加入看板'}
                </button>
                ${url ? `<a class="job-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">查看详情 →</a>` : ''}
            </div>
        </div>`;
    }

    function renderJobsList() {
        const r = state.results;
        const jobs = normalizeJobs(r.jobs);

        if (state.loadingSearch) {
            return `<div class="jobs-list">${[0, 1, 2].map(() =>
                '<div class="skeleton-row" style="height:140px;border-radius:10px"></div>'
            ).join('')}</div>`;
        }

        // 来源徽标
        const sourceBadge = r.source
            ? `<span class="source-badge ${r.source === 'real' ? 'real' : 'mock'}">${r.source === 'real' ? '真实数据' : '模拟数据'}</span>`
            : '';

        if (r.need_login && jobs.length === 0) {
            return `
                <div class="empty-card">
                    <span class="empty-emoji">🔐</span>
                    <h3>需要登录 Boss 直聘</h3>
                    <p>登录后即可搜索真实岗位数据</p>
                    <button class="btn btn-primary btn-sm" id="jobs-open-login-2" style="margin-top:0.8rem">前往登录</button>
                </div>`;
        }

        if (jobs.length === 0) {
            const kw = state.search.keyword;
            return `
                <div class="empty-card">
                    <span class="empty-emoji">🔍</span>
                    <h3>${kw ? '未找到相关岗位' : '开始搜索岗位'}</h3>
                    <p>${kw ? '试试其他关键字或更换城市' : '在上方输入关键字，点击搜索按钮'}</p>
                </div>`;
        }

        return `
        <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.9rem;">
            <span style="font-size:0.84rem;color:var(--ink-soft);">找到 <strong style="color:var(--ink)">${jobs.length}</strong> 个岗位</span>
            ${sourceBadge}
        </div>
        <div class="jobs-list">${jobs.map((j, i) => renderJobCard(j, i)).join('')}</div>
        ${renderPagination()}`;
    }

    function renderPagination() {
        const page = state.search.page;
        return `
        <div class="jobs-pagination">
            <button class="btn btn-ghost btn-sm" id="jobs-prev" ${page <= 1 ? 'disabled' : ''}>上一页</button>
            <span class="jobs-page-info">第 ${page} 页</span>
            <button class="btn btn-ghost btn-sm" id="jobs-next" ${state.results.jobs.length === 0 ? 'disabled' : ''}>下一页</button>
        </div>`;
    }

    function renderMineList() {
        if (state.loadingMine) {
            return `<div class="mine-list">${[0, 1, 2].map(() =>
                '<div class="skeleton-row" style="height:72px;border-radius:8px"></div>'
            ).join('')}</div>`;
        }
        if (state.mineApps.length === 0) {
            return `
                <div class="empty-card">
                    <span class="empty-emoji">📋</span>
                    <h3>还没有投递记录</h3>
                    <p>去 Boss 搜索页加入感兴趣的岗位吧</p>
                    <button class="btn btn-primary btn-sm" id="jobs-goto-boss" style="margin-top:0.8rem">去搜索岗位</button>
                </div>`;
        }
        return `<div class="mine-list">${state.mineApps.map(renderMineItem).join('')}</div>`;
    }

    function renderMineItem(app) {
        const status = app.status || 'applied';
        const statusLabel = pick(app, 'status_label') || STATUS_LABELS[status] || status;
        const salary = pick(app, 'salary_range', 'offer_salary');
        const loc = pick(app, 'location', 'offer_location');
        const source = app.source || '';
        const appliedTs = pick(app, 'applied_at', 'updated_at');
        const appliedMeta = formatAppliedMeta(appliedTs);

        const meta = [];
        if (salary) meta.push(`<span>${esc(salary)}</span>`);
        if (loc) meta.push(`<span>📍 ${esc(loc)}</span>`);
        if (source) meta.push(`<span>来源: ${esc(source)}</span>`);
        if (appliedMeta) meta.push(`<span title="投递于 ${esc(appliedMeta.full)}">${esc(appliedMeta.short)}</span>`);

        return `
        <div class="mine-item st-${status}">
            <div class="mine-main">
                <div class="mine-row1">
                    <span class="mine-company">${esc(app.company || '未知公司')}</span>
                    <span class="mine-status st-${status}">${esc(statusLabel)}</span>
                </div>
                <div class="mine-position">${esc(app.position || '未知职位')}</div>
                ${meta.length ? `<div class="mine-meta">${meta.join('')}</div>` : ''}
            </div>
            <button class="btn btn-ghost btn-sm" data-action="goto-kanban">在看板中查看</button>
        </div>`;
    }

    function renderTabContent() {
        if (state.tab === 'boss') {
            return renderSearchBar() + renderJobsList();
        }
        return renderMineList();
    }

    function updateTabs() {
        root.querySelectorAll('.jobs-tabs .tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === state.tab);
        });
    }

    function rerender() {
        if (!root) return;
        const banner = root.querySelector('#jobs-login-banner');
        if (banner) banner.innerHTML = renderLoginBanner();
        const content = root.querySelector('#jobs-tab-content');
        if (content) content.innerHTML = renderTabContent();
        updateTabs();
        bindDynamicEvents();
        if (Motion && Motion.revealOnScroll) Motion.revealOnScroll();
    }

    // ============ 数据加载 ============

    async function checkLogin() {
        state.loadingLogin = true;
        rerenderBanner();
        try {
            const data = await API.get('/automation/login-status');
            state.login = {
                logged_in: !!data.logged_in,
                anti_crawl: !!data.anti_crawl,
                checked: true,
            };
        } catch (e) {
            state.login = { logged_in: false, anti_crawl: false, checked: true };
        } finally {
            state.loadingLogin = false;
            rerenderBanner();
        }
    }

    function rerenderBanner() {
        if (!root) return;
        const banner = root.querySelector('#jobs-login-banner');
        if (banner) {
            banner.innerHTML = renderLoginBanner();
            const btn = banner.querySelector('#jobs-open-login');
            if (btn) btn.addEventListener('click', openLogin);
        }
    }

    async function openLogin() {
        API.toast('正在打开登录页面，请在弹出的浏览器中完成登录...', 'info', 4000);
        try {
            await API.post('/automation/open-login', { site: 'boss', headless: false });
            API.toast('登录完成，正在刷新登录状态', 'success');
            await checkLogin();
        } catch (e) {
            API.toast('打开登录页失败: ' + e.message, 'error');
        }
    }

    async function doSearch() {
        const keyword = root.querySelector('#jobs-keyword').value.trim();
        const city = root.querySelector('#jobs-city').value;
        if (!keyword) {
            API.toast('请输入搜索关键字', 'warn');
            return;
        }
        state.search.keyword = keyword;
        state.search.city = city;
        state.search.page = 1;
        state.loadingSearch = true;
        rerender();

        try {
            const data = await API.post('/automation/boss-search', {
                keyword: keyword,
                city: city,
                page: 1,
            });
            state.results = {
                jobs: data.jobs || [],
                source: data.source || '',
                need_login: !!data.need_login,
                anti_crawl: !!data.anti_crawl,
            };
            // 同步登录横幅状态
            if (data.need_login) state.login.logged_in = false;
            if (data.anti_crawl) state.login.anti_crawl = true;
            if (data.source === 'real') state.login.logged_in = true;
            state.login.checked = true;
        } catch (e) {
            state.results = { jobs: [], source: '', need_login: false, anti_crawl: false };
            API.toast('搜索失败: ' + e.message, 'error');
        } finally {
            state.loadingSearch = false;
            rerender();
        }
    }

    async function changePage(delta) {
        const next = Math.max(1, state.search.page + delta);
        if (next === state.search.page) return;
        state.search.page = next;
        state.loadingSearch = true;
        rerender();

        try {
            const data = await API.post('/automation/boss-search', {
                keyword: state.search.keyword,
                city: state.search.city,
                page: next,
            });
            state.results = {
                jobs: data.jobs || [],
                source: data.source || '',
                need_login: !!data.need_login,
                anti_crawl: !!data.anti_crawl,
            };
            if (data.need_login) state.login.logged_in = false;
            if (data.anti_crawl) state.login.anti_crawl = true;
        } catch (e) {
            API.toast('翻页失败: ' + e.message, 'error');
            // 回退页码
            state.search.page = Math.max(1, next - delta);
        } finally {
            state.loadingSearch = false;
            rerender();
        }
    }

    async function loadMineApps() {
        state.loadingMine = true;
        if (state.tab === 'mine') rerender();
        try {
            const data = await API.get('/applications/');
            state.mineApps = Array.isArray(data) ? data : (data && data.items) || [];
        } catch (e) {
            state.mineApps = [];
            API.toast('加载投递记录失败: ' + e.message, 'error');
        } finally {
            state.loadingMine = false;
            if (state.tab === 'mine') rerender();
        }
    }

    // ============ 保存到看板 ============

    async function saveToKanban(job) {
        const payload = {
            company: job.company || '',
            position: job.title || '',
            job_url: job.job_url || '',
            source: 'Boss直聘',
            status: 'applied',
            priority: 'medium',
            salary_range: job.salary || '',
            location: job.city || '',
            notes: '',
        };
        try {
            await API.post('/applications/', payload);
            if (job.job_url) state.savedIds.add(job.job_url);
            API.toast('已加入投递看板', 'success');
            rerender();
            // 若已加载过我的岗位，刷新
            if (state.mineApps.length > 0 || state.tab === 'mine') loadMineApps();
        } catch (e) {
            API.toast('加入看板失败: ' + e.message, 'error');
        }
    }

    // ============ 事件绑定 ============

    function bindEvents() {
        // Tab 切换
        root.querySelectorAll('.jobs-tabs .tab').forEach(tab => {
            tab.addEventListener('click', () => {
                state.tab = tab.dataset.tab;
                updateTabs();
                const content = root.querySelector('#jobs-tab-content');
                if (content) content.innerHTML = renderTabContent();
                bindDynamicEvents();
                if (state.tab === 'mine' && state.mineApps.length === 0 && !state.loadingMine) {
                    loadMineApps();
                }
            });
        });
    }

    function bindDynamicEvents() {
        // 登录按钮
        const loginBtn = root.querySelector('#jobs-open-login');
        if (loginBtn) loginBtn.addEventListener('click', openLogin);
        const loginBtn2 = root.querySelector('#jobs-open-login-2');
        if (loginBtn2) loginBtn2.addEventListener('click', openLogin);

        // 搜索
        const searchBtn = root.querySelector('#jobs-search-btn');
        if (searchBtn) searchBtn.addEventListener('click', doSearch);
        const keywordEl = root.querySelector('#jobs-keyword');
        if (keywordEl) {
            keywordEl.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') doSearch();
            });
        }

        // 分页
        const prevBtn = root.querySelector('#jobs-prev');
        if (prevBtn) prevBtn.addEventListener('click', () => changePage(-1));
        const nextBtn = root.querySelector('#jobs-next');
        if (nextBtn) nextBtn.addEventListener('click', () => changePage(1));

        // 岗位卡片操作
        root.querySelectorAll('.job-card').forEach(card => {
            const saveBtn = card.querySelector('[data-action="save"]');
            if (saveBtn && !saveBtn.disabled) {
                saveBtn.addEventListener('click', () => {
                    const idx = parseInt(card.dataset.idx, 10);
                    const jobs = normalizeJobs(state.results.jobs);
                    const job = jobs[idx];
                    if (job) saveToKanban(job);
                });
            }
        });

        // 跳转看板
        const gotoBoss = root.querySelector('#jobs-goto-boss');
        if (gotoBoss) gotoBoss.addEventListener('click', () => {
            state.tab = 'boss';
            rerender();
        });
        root.querySelectorAll('[data-action="goto-kanban"]').forEach(btn => {
            btn.addEventListener('click', () => {
                if (Router) Router.navigate('/kanban');
            });
        });
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        root.innerHTML = renderSkeleton();
        bindEvents();
        rerender();
        // 并行检查登录态 + 加载我的岗位（用于标记已保存）
        await Promise.all([checkLogin(), loadMineApps()]);
        // 根据已保存岗位标记 savedIds
        syncSavedIds();
    }

    function syncSavedIds() {
        state.mineApps.forEach(a => {
            if (a.job_url) state.savedIds.add(a.job_url);
        });
        if (state.tab === 'boss') rerender();
    }

    function cleanup() {
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.jobs = { mount: mount, cleanup: cleanup, title: '岗位搜索' };
})(window);
