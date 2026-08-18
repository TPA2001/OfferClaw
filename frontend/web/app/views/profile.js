/**
 * 简历画像视图 — 用户画像编辑器
 * 多 Tab 编辑：基本信息 / 教育经历 / 工作经历 / 项目经历 / 技能 / 自我评价 / 证书 / 求职意向
 * 含完成度进度条、脏状态追踪、JSON 备份
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const Motion = global.OfferClawMotion;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const CSS_ID = 'profile-styles';

    const TABS = [
        { key: 'basic',        label: '基本信息' },
        { key: 'education',    label: '教育经历' },
        { key: 'experience',   label: '工作经历' },
        { key: 'projects',     label: '项目经历' },
        { key: 'skills',       label: '技能' },
        { key: 'summary',      label: '自我评价' },
        { key: 'certificates', label: '证书' },
        { key: 'job_intent',   label: '求职意向' },
    ];

    const DEGREES = ['高中', '大专', '本科', '硕士', '博士'];
    const SKILL_LEVELS = ['了解', '熟悉', '掌握', '精通'];
    const SKILL_CATEGORIES = ['编程语言', '框架', '工具', '软技能'];
    const WORK_TYPES = ['全职', '兼职', '实习'];
    const AVAILABILITIES = ['随时', '一周内', '一个月内'];
    const GENDERS = ['男', '女'];

    const LEVEL_COLORS = {
        '了解': 'var(--ink-faint)',
        '熟悉': 'var(--olive)',
        '掌握': 'var(--olive-dark)',
        '精通': 'var(--terra)',
    };

    // ============ 状态 ============

    const state = {
        profile: null,
        completion: { overall: 0, sections: {} },
        activeTab: 'basic',
        dirty: false,
        loading: true,
        saving: false,
        error: null,
    };

    let root = null;
    let beforeUnloadHandler = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.profile-view { padding-bottom: 4rem; }

/* --- 工具栏 --- */
.profile-toolbar {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.4rem;
    padding: 0.9rem 1.2rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    flex-wrap: wrap;
}
.completion-wrap {
    flex: 1;
    min-width: 200px;
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.completion-label {
    font-size: 0.78rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
    white-space: nowrap;
}
.completion-bar {
    flex: 1;
    height: 10px;
    background: var(--paper-deep);
    border-radius: 6px;
    overflow: hidden;
    position: relative;
}
.completion-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--olive), var(--olive-dark));
    border-radius: 6px;
    width: 0%;
    transition: width 0.8s var(--ease-out);
}
.completion-pct {
    font-family: var(--font-serif);
    font-size: 1.2rem;
    font-weight: 800;
    color: var(--olive-dark);
    min-width: 48px;
    text-align: right;
}
.save-status {
    font-size: 0.78rem;
    color: var(--ink-faint);
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    white-space: nowrap;
}
.save-status.dirty { color: var(--warn); font-weight: 600; }
.save-status.saved { color: var(--success); }
.save-status .status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: currentColor;
}
.profile-toolbar .btn-save { flex-shrink: 0; }

/* --- Tab 面板 --- */
.tab-panels { min-height: 300px; }
.tab-panel { animation: profilePanelIn 0.3s var(--ease-out); }
@keyframes profilePanelIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}

/* --- 条目卡片（教育/工作/项目/证书） --- */
.entry-list {
    display: flex;
    flex-direction: column;
    gap: 0.9rem;
}
.entry-card {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1.1rem 1.3rem;
    transition: box-shadow 0.2s var(--ease), border-color 0.2s var(--ease);
}
.entry-card:hover { box-shadow: var(--shadow-sm); border-color: var(--olive); }
.entry-card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.9rem;
    padding-bottom: 0.6rem;
    border-bottom: 1px dashed var(--line-soft);
}
.entry-card-title {
    font-family: var(--font-serif);
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.entry-card-index {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--olive);
    background: var(--olive-soft);
    padding: 0.1rem 0.5rem;
    border-radius: 10px;
}
.entry-card-actions { display: flex; gap: 0.4rem; }
.entry-add-btn {
    margin-top: 0.9rem;
    width: 100%;
    padding: 0.7rem;
    border: 1px dashed var(--line);
    background: var(--paper-light);
    border-radius: 8px;
    font-size: 0.85rem;
    color: var(--ink-soft);
    cursor: pointer;
    transition: all 0.2s var(--ease);
    font-family: inherit;
}
.entry-add-btn:hover {
    border-color: var(--olive);
    color: var(--olive-dark);
    background: var(--olive-soft);
}

/* --- 技能编辑器 --- */
.skill-editor { display: flex; flex-direction: column; gap: 1rem; }
.skill-add-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
    padding: 0.8rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
}
.skill-add-input {
    flex: 1;
    min-width: 160px;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.88rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.skill-add-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: #fff;
}
.skill-add-select {
    padding: 0.5rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.82rem;
    font-family: inherit;
    cursor: pointer;
}
.skill-add-select:focus { outline: none; border-color: var(--olive); }
.skill-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    min-height: 60px;
}
.skill-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.4rem 0.5rem 0.4rem 0.75rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 18px;
    font-size: 0.82rem;
    transition: box-shadow 0.2s var(--ease), border-color 0.2s var(--ease);
}
.skill-chip:hover { box-shadow: var(--shadow-sm); border-color: var(--olive); }
.skill-chip-name { color: var(--ink); font-weight: 500; }
.skill-chip-level {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.1rem 0.45rem;
    border-radius: 10px;
    color: var(--paper-light);
}
.skill-chip-cat {
    font-size: 0.68rem;
    color: var(--ink-faint);
    padding: 0.1rem 0.35rem;
    background: var(--paper-deep);
    border-radius: 8px;
}
.skill-chip-remove {
    background: none;
    border: none;
    color: var(--ink-faint);
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0 0.2rem;
    transition: color 0.15s var(--ease);
}
.skill-chip-remove:hover { color: var(--danger); }

/* --- 标签编辑器 --- */
.tag-editor { display: flex; flex-direction: column; gap: 0.5rem; }
.tag-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    min-height: 36px;
    padding: 0.3rem 0;
}
.tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.4rem 0.3rem 0.65rem;
    background: var(--olive-soft);
    border: 1px solid var(--olive);
    border-radius: 16px;
    font-size: 0.8rem;
    color: var(--olive-dark);
    font-weight: 500;
}
.tag-chip-remove {
    background: none;
    border: none;
    color: var(--olive-dark);
    cursor: pointer;
    font-size: 0.95rem;
    line-height: 1;
    opacity: 0.6;
    transition: opacity 0.15s var(--ease);
}
.tag-chip-remove:hover { opacity: 1; color: var(--danger); }
.tag-add-input {
    padding: 0.45rem 0.7rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.85rem;
    font-family: inherit;
    flex: 1;
    min-width: 160px;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.tag-add-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: #fff;
}

/* --- JSON 备份 --- */
.json-backup {
    margin-top: 1.8rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
}
.json-backup-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.8rem 1.2rem;
    border-bottom: 1px solid var(--line-soft);
    background: var(--paper-light);
}
.json-backup-title {
    font-family: var(--font-serif);
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--ink);
}
.json-backup-actions { display: flex; gap: 0.4rem; }
.json-backup pre {
    margin: 0;
    padding: 1rem 1.2rem;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    line-height: 1.55;
    color: var(--ink-soft);
    max-height: 360px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
}

/* --- 加载/错误态 --- */
.profile-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.8rem;
    padding: 3rem 1rem;
    color: var(--ink-faint);
    font-size: 0.88rem;
}

@media (max-width: 700px) {
    .profile-toolbar { flex-direction: column; align-items: stretch; }
    .completion-wrap { width: 100%; }
    .form-grid { grid-template-columns: 1fr; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function emptyProfile() {
        return {
            basic: { name: '', gender: '', age: '', phone: '', email: '', location: '', avatar: '', job_intent: '' },
            education: [],
            experience: [],
            projects: [],
            skills: [],
            summary: { self_intro: '', strengths: '', career_goal: '', expected_salary: '', expected_location: '', expected_position: '' },
            certificates: [],
            job_intent: { target_positions: [], target_cities: [], expected_salary: '', work_type: '', availability: '' },
        };
    }

    function normalizeProfile(p) {
        if (!p || typeof p !== 'object') p = {};
        const base = emptyProfile();
        if (p.basic && typeof p.basic === 'object') {
            base.basic = Object.assign(base.basic, p.basic);
        }
        base.education = Array.isArray(p.education) ? p.education.map(normalizeEdu).filter(Boolean) : [];
        base.experience = Array.isArray(p.experience) ? p.experience.map(normalizeExp).filter(Boolean) : [];
        base.projects = Array.isArray(p.projects) ? p.projects.map(normalizeProj).filter(Boolean) : [];
        base.skills = normalizeSkills(p.skills);
        if (p.summary && typeof p.summary === 'object') {
            base.summary = Object.assign(base.summary, p.summary);
        }
        base.certificates = Array.isArray(p.certificates) ? p.certificates.map(normalizeCert).filter(Boolean) : [];
        if (p.job_intent && typeof p.job_intent === 'object') {
            base.job_intent = Object.assign(base.job_intent, p.job_intent);
            base.job_intent.target_positions = Array.isArray(base.job_intent.target_positions) ? base.job_intent.target_positions : [];
            base.job_intent.target_cities = Array.isArray(base.job_intent.target_cities) ? base.job_intent.target_cities : [];
        }
        return base;
    }

    function normalizeEdu(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            school: e.school || '',
            degree: e.degree || '',
            major: e.major || '',
            start_date: e.start_date || '',
            end_date: e.end_date || '',
            gpa: e.gpa || '',
            description: e.description || '',
        };
    }

    function normalizeExp(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            company: e.company || '',
            position: e.position || '',
            start_date: e.start_date || '',
            end_date: e.end_date || '',
            description: e.description || '',
            achievements: Array.isArray(e.achievements) ? e.achievements :
                (typeof e.achievements === 'string' ? e.achievements : ''),
        };
    }

    function normalizeProj(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            role: e.role || '',
            description: e.description || '',
            start_date: e.start_date || '',
            end_date: e.end_date || '',
            url: e.url || '',
            tech_stack: Array.isArray(e.tech_stack) ? e.tech_stack.join(', ') :
                (e.tech_stack || ''),
        };
    }

    function normalizeCert(e) {
        if (!e || typeof e !== 'object') return null;
        return {
            name: e.name || '',
            issuer: e.issuer || '',
            date: e.date || '',
            score: e.score || '',
        };
    }

    function normalizeSkills(skills) {
        if (!Array.isArray(skills)) return [];
        return skills.map(s => {
            if (typeof s === 'string') return { name: s, level: '熟悉', category: '' };
            return {
                name: s.name || '',
                level: s.level || '熟悉',
                category: s.category || '',
            };
        }).filter(s => s.name);
    }

    function markDirty() {
        if (!state.dirty) {
            state.dirty = true;
            updateSaveStatus();
        }
    }

    function achievementsToText(a) {
        if (Array.isArray(a)) return a.join('\n');
        return a || '';
    }

    function achievementsToArray(text) {
        return text.split('\n').map(s => s.trim()).filter(Boolean);
    }

    function techStackToText(ts) {
        if (Array.isArray(ts)) return ts.join(', ');
        return ts || '';
    }

    function techStackToArray(text) {
        return text.split(',').map(s => s.trim()).filter(Boolean);
    }

    // ============ 渲染：骨架 ============

    function renderShell() {
        const tabsHtml = TABS.map(t =>
            `<button class="tab ${t.key === state.activeTab ? 'active' : ''}" data-tab="${t.key}">${t.label}</button>`
        ).join('');

        return `
        <div class="view-container profile-view">
            <div class="view-header">
                <div class="header-eyebrow">PROFILE</div>
                <h1>简历画像</h1>
                <p>完善你的求职画像，Agent 将基于此生成简历与匹配岗位</p>
            </div>
            <div class="profile-toolbar">
                <div class="completion-wrap">
                    <span class="completion-label">完成度</span>
                    <div class="completion-bar">
                        <div class="completion-fill" id="completion-fill" style="width:0%"></div>
                    </div>
                    <span class="completion-pct" id="completion-pct">0%</span>
                </div>
                <span class="save-status" id="save-status">
                    <span class="status-dot"></span>
                    <span class="status-text">加载中...</span>
                </span>
                <button class="btn btn-primary btn-save" id="btn-save" disabled>保存</button>
            </div>
            <div class="tabs" id="profile-tabs">${tabsHtml}</div>
            <div class="tab-panels" id="tab-panels"></div>
            <div id="json-backup-container"></div>
        </div>`;
    }

    function renderLoading() {
        return `
        <div class="view-container profile-view">
            <div class="view-header">
                <div class="header-eyebrow">PROFILE</div>
                <h1>简历画像</h1>
                <p>完善你的求职画像，Agent 将基于此生成简历与匹配岗位</p>
            </div>
            <div class="profile-loading">
                <div class="spinner"></div>
                <span>正在加载画像数据...</span>
            </div>
        </div>`;
    }

    // ============ 渲染：工具栏状态 ============

    function updateSaveStatus() {
        const el = root.querySelector('#save-status');
        const btn = root.querySelector('#btn-save');
        if (!el || !btn) return;
        const text = el.querySelector('.status-text');
        if (state.saving) {
            el.className = 'save-status';
            text.textContent = '保存中...';
            btn.disabled = true;
            btn.textContent = '保存中...';
        } else if (state.dirty) {
            el.className = 'save-status dirty';
            text.textContent = '未保存';
            btn.disabled = false;
            btn.textContent = '保存';
        } else {
            el.className = 'save-status saved';
            text.textContent = '已保存';
            btn.disabled = false;
            btn.textContent = '保存';
        }
    }

    function updateCompletion() {
        const fill = root.querySelector('#completion-fill');
        const pct = root.querySelector('#completion-pct');
        const overall = Math.max(0, Math.min(100, state.completion.overall || 0));
        if (fill) fill.style.width = overall + '%';
        if (pct) {
            pct.textContent = overall + '%';
            if (Motion && Motion.countUp) {
                Motion.countUp(pct, overall, { duration: 800, suffix: '%' });
            }
        }
    }

    // ============ 渲染：Tab 面板 ============

    function renderTabPanel() {
        const container = root.querySelector('#tab-panels');
        if (!container) return;
        const tab = state.activeTab;
        let html = '';
        switch (tab) {
            case 'basic':        html = renderBasicTab(); break;
            case 'education':    html = renderEducationTab(); break;
            case 'experience':   html = renderExperienceTab(); break;
            case 'projects':     html = renderProjectsTab(); break;
            case 'skills':       html = renderSkillsTab(); break;
            case 'summary':      html = renderSummaryTab(); break;
            case 'certificates': html = renderCertificatesTab(); break;
            case 'job_intent':   html = renderJobIntentTab(); break;
        }
        container.innerHTML = '<div class="tab-panel">' + html + '</div>';
        bindPanelEvents();
        if (Motion && Motion.tabEnter) {
            const panel = container.querySelector('.tab-panel');
            if (panel) Motion.tabEnter(panel);
        }
    }

    // --- 基本信息 ---

    function renderBasicTab() {
        const b = state.profile.basic;
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">基本信息</h2>
            </div>
            <div class="form-grid">
                <div class="form-field">
                    <label>姓名</label>
                    <input type="text" data-section="basic" data-field="name" value="${esc(b.name)}" placeholder="你的姓名">
                </div>
                <div class="form-field">
                    <label>性别</label>
                    <select data-section="basic" data-field="gender">
                        <option value="">未设置</option>
                        ${GENDERS.map(g => `<option value="${g}" ${b.gender === g ? 'selected' : ''}>${g}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>年龄</label>
                    <input type="number" data-section="basic" data-field="age" value="${esc(b.age)}" placeholder="如 24" min="0" max="120">
                </div>
                <div class="form-field">
                    <label>手机号</label>
                    <input type="tel" data-section="basic" data-field="phone" value="${esc(b.phone)}" placeholder="11 位手机号">
                </div>
                <div class="form-field">
                    <label>邮箱</label>
                    <input type="email" data-section="basic" data-field="email" value="${esc(b.email)}" placeholder="your@email.com">
                </div>
                <div class="form-field">
                    <label>所在城市</label>
                    <input type="text" data-section="basic" data-field="location" value="${esc(b.location)}" placeholder="如 北京">
                </div>
                <div class="form-field">
                    <label>头像 URL</label>
                    <input type="url" data-section="basic" data-field="avatar" value="${esc(b.avatar)}" placeholder="https://...">
                </div>
                <div class="form-field">
                    <label>当前求职意向</label>
                    <input type="text" data-section="basic" data-field="job_intent" value="${esc(b.job_intent)}" placeholder="如 后端工程师">
                </div>
            </div>
        </div>`;
    }

    // --- 教育经历 ---

    function renderEducationTab() {
        const list = state.profile.education;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">🎓</span><h3>暂无教育经历</h3><p>点击下方按钮添加第一条记录</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">教育经历 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="education" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>学校</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="school" value="${esc(e.school)}" placeholder="如 清华大学">
                        </div>
                        <div class="form-field">
                            <label>学历</label>
                            <select data-section="education" data-index="${i}" data-field="degree">
                                <option value="">请选择</option>
                                ${DEGREES.map(d => `<option value="${d}" ${e.degree === d ? 'selected' : ''}>${d}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-field">
                            <label>专业</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="major" value="${esc(e.major)}" placeholder="如 计算机科学">
                        </div>
                        <div class="form-field">
                            <label>GPA</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="gpa" value="${esc(e.gpa)}" placeholder="如 3.8/4.0">
                        </div>
                        <div class="form-field">
                            <label>开始时间</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="start_date" value="${esc(e.start_date)}" placeholder="如 2020-09">
                        </div>
                        <div class="form-field">
                            <label>结束时间</label>
                            <input type="text" data-section="education" data-index="${i}" data-field="end_date" value="${esc(e.end_date)}" placeholder="如 2024-06 或 至今">
                        </div>
                        <div class="form-field full">
                            <label>描述</label>
                            <textarea data-section="education" data-index="${i}" data-field="description" placeholder="主修课程、学术成就等">${esc(e.description)}</textarea>
                        </div>
                    </div>
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="education">+ 添加教育经历</button>`;
        return html;
    }

    // --- 工作经历 ---

    function renderExperienceTab() {
        const list = state.profile.experience;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">💼</span><h3>暂无工作经历</h3><p>点击下方按钮添加第一条记录</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">工作经历 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="experience" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>公司</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="company" value="${esc(e.company)}" placeholder="如 字节跳动">
                        </div>
                        <div class="form-field">
                            <label>职位</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="position" value="${esc(e.position)}" placeholder="如 后端工程师">
                        </div>
                        <div class="form-field">
                            <label>开始时间</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="start_date" value="${esc(e.start_date)}" placeholder="如 2023-06">
                        </div>
                        <div class="form-field">
                            <label>结束时间</label>
                            <input type="text" data-section="experience" data-index="${i}" data-field="end_date" value="${esc(e.end_date)}" placeholder="如 2024-03 或 至今">
                        </div>
                        <div class="form-field full">
                            <label>工作描述</label>
                            <textarea data-section="experience" data-index="${i}" data-field="description" placeholder="工作职责与日常内容">${esc(e.description)}</textarea>
                        </div>
                        <div class="form-field full">
                            <label>主要成就（每行一条）</label>
                            <textarea data-section="experience" data-index="${i}" data-field="achievements" data-type="text-array" placeholder="每行一条成就，如：&#10;优化了 XX 接口性能提升 50%&#10;主导了 XX 项目的从 0 到 1">${esc(achievementsToText(e.achievements))}</textarea>
                        </div>
                    </div>
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="experience">+ 添加工作经历</button>`;
        return html;
    }

    // --- 项目经历 ---

    function renderProjectsTab() {
        const list = state.profile.projects;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">📦</span><h3>暂无项目经历</h3><p>点击下方按钮添加第一条记录</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">项目经历 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="projects" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>项目名称</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 OfferClaw 求职助手">
                        </div>
                        <div class="form-field">
                            <label>角色</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="role" value="${esc(e.role)}" placeholder="如 全栈开发 / 负责人">
                        </div>
                        <div class="form-field">
                            <label>开始时间</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="start_date" value="${esc(e.start_date)}" placeholder="如 2024-01">
                        </div>
                        <div class="form-field">
                            <label>结束时间</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="end_date" value="${esc(e.end_date)}" placeholder="如 2024-06 或 至今">
                        </div>
                        <div class="form-field full">
                            <label>项目链接</label>
                            <input type="url" data-section="projects" data-index="${i}" data-field="url" value="${esc(e.url)}" placeholder="https://github.com/...">
                        </div>
                        <div class="form-field full">
                            <label>技术栈（逗号分隔）</label>
                            <input type="text" data-section="projects" data-index="${i}" data-field="tech_stack" data-type="csv-array" value="${esc(techStackToText(e.tech_stack))}" placeholder="如 Python, FastAPI, React">
                        </div>
                        <div class="form-field full">
                            <label>项目描述</label>
                            <textarea data-section="projects" data-index="${i}" data-field="description" placeholder="项目背景、你的贡献、技术亮点">${esc(e.description)}</textarea>
                        </div>
                    </div>
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="projects">+ 添加项目经历</button>`;
        return html;
    }

    // --- 技能 ---

    function renderSkillsTab() {
        const skills = state.profile.skills;
        let chipsHtml = '';
        if (skills.length === 0) {
            chipsHtml = '<span style="color:var(--ink-faint);font-size:0.85rem;padding:0.5rem 0">暂未添加技能，在上方输入后按回车添加</span>';
        } else {
            chipsHtml = skills.map((s, i) => {
                const lvl = s.level || '熟悉';
                const lvlColor = LEVEL_COLORS[lvl] || 'var(--olive)';
                return `
                <div class="skill-chip">
                    <span class="skill-chip-name">${esc(s.name)}</span>
                    <span class="skill-chip-level" style="background:${lvlColor}">${esc(lvl)}</span>
                    ${s.category ? `<span class="skill-chip-cat">${esc(s.category)}</span>` : ''}
                    <button class="skill-chip-remove" data-action="delete-skill" data-index="${i}" title="删除">×</button>
                </div>`;
            }).join('');
        }

        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">技能管理</h2>
            </div>
            <div class="skill-editor">
                <div class="skill-add-row">
                    <input type="text" class="skill-add-input" id="skill-name-input" placeholder="输入技能名称，如 Python，按回车添加">
                    <select class="skill-add-select" id="skill-level-select">
                        ${SKILL_LEVELS.map(l => `<option value="${l}">${l}</option>`).join('')}
                    </select>
                    <select class="skill-add-select" id="skill-category-select">
                        ${SKILL_CATEGORIES.map(c => `<option value="${c}">${c}</option>`).join('')}
                    </select>
                    <button class="btn btn-primary btn-sm" id="skill-add-btn">添加技能</button>
                </div>
                <div class="skill-chips" id="skill-chips">${chipsHtml}</div>
            </div>
        </div>`;
    }

    // --- 自我评价 ---

    function renderSummaryTab() {
        const s = state.profile.summary;
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">自我评价</h2>
            </div>
            <div class="form-grid">
                <div class="form-field full">
                    <label>自我介绍</label>
                    <textarea data-section="summary" data-field="self_intro" rows="4" placeholder="一段简短的自我介绍，让 HR 快速了解你">${esc(s.self_intro)}</textarea>
                </div>
                <div class="form-field full">
                    <label>核心优势（每行一条）</label>
                    <textarea data-section="summary" data-field="strengths" rows="4" placeholder="你的核心竞争力，如：&#10;扎实的算法与数据结构基础&#10;3 年后端开发经验">${esc(s.strengths)}</textarea>
                </div>
                <div class="form-field full">
                    <label>职业目标</label>
                    <textarea data-section="summary" data-field="career_goal" rows="3" placeholder="你的中长期职业规划">${esc(s.career_goal)}</textarea>
                </div>
                <div class="form-field">
                    <label>期望薪资</label>
                    <input type="text" data-section="summary" data-field="expected_salary" value="${esc(s.expected_salary)}" placeholder="如 20-30K">
                </div>
                <div class="form-field">
                    <label>期望城市</label>
                    <input type="text" data-section="summary" data-field="expected_location" value="${esc(s.expected_location)}" placeholder="如 北京/上海">
                </div>
                <div class="form-field">
                    <label>期望职位</label>
                    <input type="text" data-section="summary" data-field="expected_position" value="${esc(s.expected_position)}" placeholder="如 高级后端工程师">
                </div>
            </div>
        </div>`;
    }

    // --- 证书 ---

    function renderCertificatesTab() {
        const list = state.profile.certificates;
        let html = '<div class="entry-list">';
        if (list.length === 0) {
            html += `<div class="empty-card"><span class="empty-emoji">📜</span><h3>暂无证书</h3><p>点击下方按钮添加你的证书</p></div>`;
        } else {
            list.forEach((e, i) => {
                html += `
                <div class="entry-card">
                    <div class="entry-card-head">
                        <span class="entry-card-title">证书 <span class="entry-card-index">#${i + 1}</span></span>
                        <div class="entry-card-actions">
                            <button class="btn btn-danger btn-sm" data-action="delete-entry" data-section="certificates" data-index="${i}">删除</button>
                        </div>
                    </div>
                    <div class="form-grid">
                        <div class="form-field">
                            <label>证书名称</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="name" value="${esc(e.name)}" placeholder="如 软件设计师">
                        </div>
                        <div class="form-field">
                            <label>颁发机构</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="issuer" value="${esc(e.issuer)}" placeholder="如 工信部">
                        </div>
                        <div class="form-field">
                            <label>获得日期</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="date" value="${esc(e.date)}" placeholder="如 2023-06">
                        </div>
                        <div class="form-field">
                            <label>成绩/分数</label>
                            <input type="text" data-section="certificates" data-index="${i}" data-field="score" value="${esc(e.score)}" placeholder="如 优秀 / 90">
                        </div>
                    </div>
                </div>`;
            });
        }
        html += `</div>
        <button class="entry-add-btn" data-action="add-entry" data-section="certificates">+ 添加证书</button>`;
        return html;
    }

    // --- 求职意向 ---

    function renderJobIntentTab() {
        const j = state.profile.job_intent;
        return `
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">求职意向</h2>
            </div>
            <div class="form-grid">
                <div class="form-field full">
                    <label>目标职位</label>
                    <div class="tag-editor">
                        <div class="tag-chips" id="tag-positions">
                            ${(j.target_positions || []).map((p, i) =>
                                `<div class="tag-chip"><span>${esc(p)}</span><button class="tag-chip-remove" data-action="delete-tag" data-field="target_positions" data-index="${i}" title="删除">×</button></div>`
                            ).join('')}
                        </div>
                        <input type="text" class="tag-add-input" id="input-positions" placeholder="输入职位后按回车添加，如 后端工程师" data-field="target_positions">
                    </div>
                </div>
                <div class="form-field full">
                    <label>目标城市</label>
                    <div class="tag-editor">
                        <div class="tag-chips" id="tag-cities">
                            ${(j.target_cities || []).map((c, i) =>
                                `<div class="tag-chip"><span>${esc(c)}</span><button class="tag-chip-remove" data-action="delete-tag" data-field="target_cities" data-index="${i}" title="删除">×</button></div>`
                            ).join('')}
                        </div>
                        <input type="text" class="tag-add-input" id="input-cities" placeholder="输入城市后按回车添加，如 北京" data-field="target_cities">
                    </div>
                </div>
                <div class="form-field">
                    <label>期望薪资</label>
                    <input type="text" data-section="job_intent" data-field="expected_salary" value="${esc(j.expected_salary)}" placeholder="如 20-30K">
                </div>
                <div class="form-field">
                    <label>工作类型</label>
                    <select data-section="job_intent" data-field="work_type">
                        <option value="">请选择</option>
                        ${WORK_TYPES.map(w => `<option value="${w}" ${j.work_type === w ? 'selected' : ''}>${w}</option>`).join('')}
                    </select>
                </div>
                <div class="form-field">
                    <label>到岗时间</label>
                    <select data-section="job_intent" data-field="availability">
                        <option value="">请选择</option>
                        ${AVAILABILITIES.map(a => `<option value="${a}" ${j.availability === a ? 'selected' : ''}>${a}</option>`).join('')}
                    </select>
                </div>
            </div>
        </div>`;
    }

    // --- JSON 备份 ---

    function renderJsonBackup() {
        const container = root.querySelector('#json-backup-container');
        if (!container) return;
        const json = JSON.stringify(state.profile, null, 2);
        container.innerHTML = `
        <div class="json-backup">
            <div class="json-backup-head">
                <span class="json-backup-title">JSON 备份</span>
                <div class="json-backup-actions">
                    <button class="btn btn-ghost btn-sm" id="btn-copy-json">复制 JSON</button>
                    <button class="btn btn-ghost btn-sm" id="btn-download-json">下载文件</button>
                </div>
            </div>
            <pre>${esc(json)}</pre>
        </div>`;

        const copyBtn = container.querySelector('#btn-copy-json');
        if (copyBtn) {
            copyBtn.onclick = async () => {
                try {
                    await navigator.clipboard.writeText(json);
                    API.toast('JSON 已复制到剪贴板', 'success');
                } catch (e) {
                    // Fallback
                    const ta = document.createElement('textarea');
                    ta.value = json;
                    document.body.appendChild(ta);
                    ta.select();
                    try {
                        document.execCommand('copy');
                        API.toast('JSON 已复制到剪贴板', 'success');
                    } catch (e2) {
                        API.toast('复制失败，请手动选择文本', 'error');
                    }
                    ta.remove();
                }
            };
        }

        const dlBtn = container.querySelector('#btn-download-json');
        if (dlBtn) {
            dlBtn.onclick = () => {
                const blob = new Blob([json], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'offerclaw-profile-' + new Date().toISOString().slice(0, 10) + '.json';
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                API.toast('已开始下载', 'success');
            };
        }
    }

    // ============ 事件绑定 ============

    function bindEvents() {
        // Tab 切换
        const tabsEl = root.querySelector('#profile-tabs');
        if (tabsEl) {
            tabsEl.addEventListener('click', (e) => {
                const tab = e.target.closest('.tab');
                if (!tab) return;
                const key = tab.dataset.tab;
                if (key && key !== state.activeTab) {
                    state.activeTab = key;
                    updateTabsUI();
                    renderTabPanel();
                }
            });
        }

        // 保存按钮
        const saveBtn = root.querySelector('#btn-save');
        if (saveBtn) {
            saveBtn.addEventListener('click', saveProfile);
        }
    }

    function updateTabsUI() {
        root.querySelectorAll('#profile-tabs .tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === state.activeTab);
        });
    }

    function bindPanelEvents() {
        const panel = root.querySelector('#tab-panels');
        if (!panel) return;

        // 表单字段变更（委托）
        panel.addEventListener('input', onFieldInput);
        panel.addEventListener('change', onFieldInput);

        // 添加/删除条目
        panel.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            const action = btn.dataset.action;
            if (action === 'add-entry') {
                addEntry(btn.dataset.section);
            } else if (action === 'delete-entry') {
                deleteEntry(btn.dataset.section, parseInt(btn.dataset.index, 10));
            } else if (action === 'delete-skill') {
                deleteSkill(parseInt(btn.dataset.index, 10));
            } else if (action === 'delete-tag') {
                deleteTag(btn.dataset.field, parseInt(btn.dataset.index, 10));
            }
        });

        // 技能添加
        const skillInput = panel.querySelector('#skill-name-input');
        const skillAddBtn = panel.querySelector('#skill-add-btn');
        if (skillInput) {
            skillInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addSkill();
                }
            });
        }
        if (skillAddBtn) {
            skillAddBtn.addEventListener('click', addSkill);
        }

        // 标签添加（职位/城市）
        panel.querySelectorAll('.tag-add-input').forEach(input => {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addTag(input.dataset.field, input.value.trim());
                    input.value = '';
                }
            });
        });
    }

    function onFieldInput(e) {
        const el = e.target;
        if (!el || !el.dataset || !el.dataset.field) return;
        // 排除标签添加输入框
        if (el.classList.contains('tag-add-input')) return;
        handleFieldChange(el);
    }

    function handleFieldChange(el) {
        const section = el.dataset.section;
        const field = el.dataset.field;
        const index = el.dataset.index;
        const type = el.dataset.type;
        let value = el.value;

        if (type === 'text-array') {
            value = achievementsToArray(value);
        } else if (type === 'csv-array') {
            value = techStackToArray(value);
        } else if (el.type === 'number') {
            value = value === '' ? '' : Number(value);
        }

        if (index !== undefined) {
            const idx = parseInt(index, 10);
            if (state.profile[section] && state.profile[section][idx]) {
                state.profile[section][idx][field] = value;
            }
        } else {
            if (state.profile[section]) {
                state.profile[section][field] = value;
            }
        }
        markDirty();
    }

    // ============ 条目操作 ============

    function addEntry(section) {
        const templates = {
            education: { school: '', degree: '', major: '', start_date: '', end_date: '', gpa: '', description: '' },
            experience: { company: '', position: '', start_date: '', end_date: '', description: '', achievements: [] },
            projects: { name: '', role: '', description: '', start_date: '', end_date: '', url: '', tech_stack: [] },
            certificates: { name: '', issuer: '', date: '', score: '' },
        };
        if (!templates[section]) return;
        state.profile[section].push(templates[section]);
        markDirty();
        renderTabPanel();
        API.toast('已添加新条目', 'info', 1500);
    }

    function deleteEntry(section, index) {
        if (!state.profile[section] || !state.profile[section][index]) return;
        if (!confirm('确定删除此条目？')) return;
        state.profile[section].splice(index, 1);
        markDirty();
        renderTabPanel();
        API.toast('已删除', 'success', 1500);
    }

    // ============ 技能操作 ============

    function addSkill() {
        const nameEl = root.querySelector('#skill-name-input');
        const levelEl = root.querySelector('#skill-level-select');
        const catEl = root.querySelector('#skill-category-select');
        if (!nameEl) return;
        const name = nameEl.value.trim();
        if (!name) {
            API.toast('请输入技能名称', 'warn');
            return;
        }
        // 去重
        if (state.profile.skills.some(s => s.name === name)) {
            API.toast('该技能已存在', 'warn');
            return;
        }
        state.profile.skills.push({
            name: name,
            level: levelEl ? levelEl.value : '熟悉',
            category: catEl ? catEl.value : '',
        });
        markDirty();
        renderTabPanel();
        nameEl.value = '';
        nameEl.focus();
    }

    function deleteSkill(index) {
        if (!state.profile.skills[index]) return;
        state.profile.skills.splice(index, 1);
        markDirty();
        renderTabPanel();
    }

    // ============ 标签操作 ============

    function addTag(field, value) {
        if (!value) return;
        const arr = state.profile.job_intent[field];
        if (!Array.isArray(arr)) return;
        if (arr.includes(value)) {
            API.toast('已存在', 'warn');
            return;
        }
        arr.push(value);
        markDirty();
        renderTabPanel();
        // 重新聚焦输入框
        const inputId = field === 'target_positions' ? '#input-positions' : '#input-cities';
        const input = root.querySelector(inputId);
        if (input) input.focus();
    }

    function deleteTag(field, index) {
        const arr = state.profile.job_intent[field];
        if (!Array.isArray(arr) || !arr[index]) return;
        arr.splice(index, 1);
        markDirty();
        renderTabPanel();
    }

    // ============ 数据加载与保存 ============

    async function loadProfile() {
        state.loading = true;
        state.error = null;
        root.innerHTML = renderLoading();
        try {
            const [profile, completion] = await Promise.all([
                API.get('/profiles/'),
                API.get('/profiles/completion').catch(() => ({ overall: 0, sections: {} })),
            ]);
            state.profile = normalizeProfile(profile);
            state.completion = completion || { overall: 0, sections: {} };
            state.dirty = false;
            state.loading = false;
            renderAll();
        } catch (e) {
            state.loading = false;
            state.error = e.message || '加载失败';
            // 初始化空画像供编辑
            state.profile = emptyProfile();
            state.completion = { overall: 0, sections: {} };
            state.dirty = false;
            root.innerHTML = renderShell();
            bindEvents();
            renderTabPanel();
            renderJsonBackup();
            updateSaveStatus();
            updateCompletion();
            API.toast('画像数据加载失败，已初始化空画像: ' + state.error, 'warn', 4000);
        }
    }

    async function loadCompletion() {
        try {
            const data = await API.get('/profiles/completion');
            state.completion = data || { overall: 0, sections: {} };
            updateCompletion();
        } catch (e) {
            // 静默失败
        }
    }

    async function saveProfile() {
        if (!state.dirty || state.saving) return;
        state.saving = true;
        updateSaveStatus();
        try {
            // 清理 achievements 和 tech_stack 数组化
            const payload = JSON.parse(JSON.stringify(state.profile));
            payload.experience = (payload.experience || []).map(e => ({
                ...e,
                achievements: Array.isArray(e.achievements) ? e.achievements :
                    (typeof e.achievements === 'string' ? achievementsToArray(e.achievements) : []),
            }));
            payload.projects = (payload.projects || []).map(p => ({
                ...p,
                tech_stack: Array.isArray(p.tech_stack) ? p.tech_stack :
                    (typeof p.tech_stack === 'string' ? techStackToArray(p.tech_stack) : []),
            }));

            await API.post('/profiles/', payload);
            state.dirty = false;
            API.toast('画像已保存', 'success');
            await loadCompletion();
        } catch (e) {
            API.toast('保存失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.saving = false;
            updateSaveStatus();
        }
    }

    // ============ 全量渲染 ============

    function renderAll() {
        if (!root) return;
        root.innerHTML = renderShell();
        bindEvents();
        renderTabPanel();
        renderJsonBackup();
        updateSaveStatus();
        // 延迟更新完成度以确保过渡动画
        requestAnimationFrame(() => updateCompletion());
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();

        // 脏状态离开警告
        beforeUnloadHandler = (e) => {
            if (state.dirty) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        global.addEventListener('beforeunload', beforeUnloadHandler);

        await loadProfile();
    }

    function cleanup() {
        if (beforeUnloadHandler) {
            global.removeEventListener('beforeunload', beforeUnloadHandler);
            beforeUnloadHandler = null;
        }
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.profile = { mount, cleanup, title: '简历画像' };
})(window);
