/**
 * 设置视图 — 系统设置与诊断
 * 外观主题 / 系统健康 / LLM 配置 / LLM 测试 / 数据统计 / 关于 / 危险操作
 */
(function (global) {
    'use strict';

    const API = global.OfferCabinAPI;
    const Motion = global.OfferCabinMotion;
    const Theme = global.OfferCabinTheme;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const CSS_ID = 'settings-styles';

    const PROJECT_INFO = {
        name: 'OfferCabin',
        version: '',
        repo: 'https://github.com/your-org/offercabin',
        description: '求职投递看板：投递管理 + 画像 + 面试复盘 + Agent 助手',
    };

    // ============ 状态 ============

    const state = {
        health: null,
        loadingHealth: true,
        stats: { applications: 0, sessions: 0, completion: 0 },
        loadingStats: true,
        testing: false,
        testResult: null,
        testMockMode: false,
        // 外观
        currentTheme: 'paper',
        currentDensity: 'comfortable',
        currentAccent: '',
        // LLM 配置
        llmConfig: null,
        loadingLlmConfig: true,
        savingLlm: false,
        llmSaveStatus: null,
    };

    let root = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.settings-view { padding-bottom: 4rem; }

/* --- 区块 --- */
.settings-section {
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
    transition: box-shadow 0.2s var(--ease);
}
.settings-section:hover { box-shadow: var(--shadow-sm); }
.settings-section.danger {
    border-color: var(--danger);
    border-left: 3px solid var(--danger);
}
.settings-section.danger:hover { box-shadow: 0 4px 16px rgba(185, 74, 58, 0.12); }
.section-title {
    font-family: var(--font-serif);
    font-size: 1rem;
    font-weight: 700;
    color: var(--ink);
    margin-bottom: 1rem;
    padding-bottom: 0.6rem;
    border-bottom: 1px dashed var(--line-soft);
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.section-title .title-icon {
    font-size: 1.1rem;
    line-height: 1;
}
.section-title .title-tag {
    font-size: 0.7rem;
    font-family: var(--font-mono);
    font-weight: 500;
    color: var(--ink-faint);
    background: var(--paper-deep);
    padding: 0.1rem 0.5rem;
    border-radius: 8px;
    margin-left: auto;
}
/* --- 系统诊断（折叠区） --- */
.diag-toggle-hint {
    font-size: 0.68rem;
    font-family: var(--font-mono);
    font-weight: 500;
    color: var(--ink-faint);
    background: var(--paper-deep);
    padding: 0.1rem 0.5rem;
    border-radius: 8px;
    margin-left: auto;
}
.diag-body { animation: settings-fade 0.2s var(--ease); }
.diag-stats { margin-bottom: 0.2rem; }
.diag-divider { height: 1px; background: var(--line-soft); margin: 0.9rem 0 0.6rem; }
@keyframes settings-fade { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }

/* --- 健康状态行 --- */
.health-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--line-soft);
    font-size: 0.86rem;
}
.health-row:last-child { border-bottom: none; }
.health-label {
    color: var(--ink-soft);
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.health-value {
    color: var(--ink);
    font-weight: 500;
    font-family: var(--font-mono);
    font-size: 0.82rem;
}
.health-value.ok { color: var(--success); }
.health-value.err { color: var(--danger); }
.health-value.warn { color: var(--warn); }
.status-dot-lg {
    width: 10px; height: 10px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}
.status-dot-lg.ok { background: var(--success); box-shadow: 0 0 0 3px rgba(90, 122, 58, 0.15); }
.status-dot-lg.err { background: var(--danger); box-shadow: 0 0 0 3px rgba(185, 74, 58, 0.15); }
.status-dot-lg.warn { background: var(--warn); box-shadow: 0 0 0 3px rgba(184, 134, 11, 0.15); }
.status-dot-lg.pending { background: var(--ink-faint); }

/* --- LLM 测试区 --- */
.llm-test-area {
    margin-top: 0.9rem;
    padding-top: 0.9rem;
    border-top: 1px dashed var(--line-soft);
}
.llm-test-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.7rem;
}
.llm-test-result {
    padding: 0.8rem 1rem;
    background: var(--paper-light);
    border: 1px solid var(--line);
    border-radius: 8px;
    font-size: 0.84rem;
    line-height: 1.6;
    color: var(--ink);
    white-space: pre-wrap;
    word-break: break-word;
    min-height: 48px;
    max-height: 200px;
    overflow-y: auto;
}
.llm-test-result.empty {
    color: var(--ink-faint);
    font-style: italic;
    display: flex;
    align-items: center;
    justify-content: center;
}
.llm-test-result.error {
    border-color: var(--danger);
    background: var(--terra-soft);
    color: var(--terra-deep);
}
.llm-test-result.streaming {
    border-color: var(--olive);
    background: var(--olive-soft);
}
.llm-mock-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.2rem 0.55rem;
    border-radius: 10px;
    background: var(--warn);
    color: var(--paper-light);
}
.llm-config-hint {
    margin-top: 0.7rem;
    padding: 0.7rem 0.9rem;
    background: var(--paper-deep);
    border-radius: 6px;
    font-size: 0.8rem;
    color: var(--ink-soft);
    line-height: 1.7;
}
.llm-config-hint code {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    background: var(--card);
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    border: 1px solid var(--line);
    color: var(--olive-dark);
}

/* --- LLM 预设模板 --- */
.llm-template-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
}
.llm-template-row select {
    flex: 0 1 auto;
    min-width: 220px;
    padding: 0.5rem 0.7rem;
    font-size: 0.84rem;
    color: var(--ink);
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    font-family: var(--font-sans);
}
.llm-template-row select:focus { outline: none; border-color: var(--olive); }
.llm-template-note {
    font-size: 0.74rem;
    color: var(--ink-faint);
    font-family: var(--font-sans);
}
.llm-divider {
    height: 1px;
    background: var(--line-soft);
    margin: 0.9rem 0 1rem;
}

/* --- 数据统计 --- */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.8rem;
}
.stat-cell {
    text-align: center;
    padding: 1rem 0.5rem;
    background: var(--paper-light);
    border: 1px solid var(--line-soft);
    border-radius: 8px;
    transition: border-color 0.2s var(--ease);
}
.stat-cell:hover { border-color: var(--olive); }
.stat-cell-label {
    font-size: 0.76rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.3rem;
}
.stat-cell-value {
    font-family: var(--font-serif);
    font-size: 2rem;
    font-weight: 900;
    color: var(--olive-dark);
    line-height: 1.1;
}
.stat-cell-sub {
    font-size: 0.72rem;
    color: var(--ink-faint);
    margin-top: 0.2rem;
}

/* --- 关于 --- */
.about-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    font-size: 0.86rem;
    border-bottom: 1px solid var(--line-soft);
}
.about-row:last-child { border-bottom: none; }
.about-label { color: var(--ink-soft); }
.about-value { color: var(--ink); font-weight: 500; }
.about-value a {
    color: var(--olive);
    text-decoration: none;
    transition: color 0.15s var(--ease);
}
.about-value a:hover { color: var(--olive-dark); text-decoration: underline; }
.about-desc {
    margin-top: 0.6rem;
    padding: 0.7rem 0.9rem;
    background: var(--paper-light);
    border-radius: 6px;
    font-size: 0.82rem;
    color: var(--ink-soft);
    line-height: 1.6;
}

/* --- 支持本项目 --- */
.support-intro {
    font-size: 0.86rem;
    color: var(--ink-soft);
    line-height: 1.75;
    margin-bottom: 1.1rem;
}
.donate-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
    max-width: 360px;
}
.donate-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
}
.donate-qr {
    width: 150px;
    height: 150px;
    object-fit: contain;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 6px;
    cursor: zoom-in;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.donate-qr:hover {
    border-color: var(--olive);
    box-shadow: var(--shadow-md);
}
.donate-label {
    font-size: 0.8rem;
    color: var(--ink-soft);
    font-family: var(--font-mono);
    letter-spacing: 0.5px;
}
.donate-note {
    margin-top: 1rem;
    padding-top: 0.8rem;
    border-top: 1px dashed var(--line-soft);
    font-size: 0.76rem;
    color: var(--ink-faint);
    text-align: center;
}

/* 赞赏码浮层 */
.donate-modal {
    position: fixed;
    inset: 0;
    z-index: 1000;
    display: grid;
    place-items: center;
    background: rgba(18, 20, 28, 0.78);
    -webkit-backdrop-filter: blur(5px);
    backdrop-filter: blur(5px);
    cursor: zoom-out;
    animation: donateFade 0.18s var(--ease);
}
.donate-modal img {
    max-width: min(82vw, 460px);
    max-height: 80vh;
    object-fit: contain;
    background: var(--card);
    border-radius: 16px;
    padding: 12px;
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
    animation: donatePop 0.18s var(--ease);
}
.donate-modal .donate-modal-cap {
    position: absolute;
    bottom: 9vh;
    left: 0;
    right: 0;
    text-align: center;
    color: var(--paper-light);
    font-family: var(--font-mono);
    font-size: 0.82rem;
    letter-spacing: 0.5px;
    opacity: 0.85;
}
@keyframes donateFade { from { opacity: 0; } }
@keyframes donatePop { from { opacity: 0; transform: scale(0.92); } }
@media (prefers-reduced-motion: reduce) {
    .donate-modal, .donate-modal img { animation: none; }
}

/* --- 危险操作 --- */
.danger-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.7rem 0;
    border-bottom: 1px solid var(--line-soft);
    gap: 1rem;
}
.danger-item:last-child { border-bottom: none; }
.danger-info { flex: 1; min-width: 0; }
.danger-title {
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 0.15rem;
}
.danger-desc {
    font-size: 0.78rem;
    color: var(--ink-soft);
    line-height: 1.5;
}

/* --- 加载态 --- */
.settings-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.8rem;
    padding: 2rem 1rem;
    color: var(--ink-faint);
    font-size: 0.85rem;
}
.skeleton-line {
    height: 14px;
    background: linear-gradient(90deg, var(--line-soft) 25%, var(--paper-deep) 50%, var(--line-soft) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    margin-bottom: 0.6rem;
}

@media (max-width: 700px) {
    .stats-grid { grid-template-columns: 1fr; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function formatUptime(seconds) {
        if (!seconds || seconds <= 0) return '未知';
        const s = Math.floor(seconds);
        const days = Math.floor(s / 86400);
        const hours = Math.floor((s % 86400) / 3600);
        const mins = Math.floor((s % 3600) / 60);
        if (days > 0) return days + ' 天 ' + hours + ' 小时';
        if (hours > 0) return hours + ' 小时 ' + mins + ' 分';
        if (mins > 0) return mins + ' 分钟';
        return s + ' 秒';
    }

    function getHealthStatus(h) {
        if (!h) return { cls: 'pending', text: '检测中' };
        const status = (h.status || '').toLowerCase();
        if (status === 'ok' || status === 'healthy') return { cls: 'ok', text: '运行中' };
        if (status === 'degraded') return { cls: 'warn', text: '降级' };
        return { cls: 'err', text: status || '异常' };
    }

    function getDbStatus(h) {
        if (!h) return { cls: 'pending', text: '未知' };
        if (h.database !== undefined) {
            const dbOk = h.database === true || h.database === 'ok' || h.database === 'connected';
            return { cls: dbOk ? 'ok' : 'err', text: dbOk ? '已连接' : '断开' };
        }
        if (h.database_status) {
            const s = h.database_status.toLowerCase();
            return { cls: s === 'ok' || s === 'connected' ? 'ok' : 'err', text: h.database_status };
        }
        // 健康状态本身可用作 DB 代理
        if (h.status === 'ok' || h.status === 'healthy') return { cls: 'ok', text: '正常' };
        return { cls: 'pending', text: '未知' };
    }

    function getLlmInfo(h) {
        if (!h) return { configured: false, model: '', provider: '', mock: false };
        const configured = h.llm_configured === true || h.llm_ready === true;
        const modelInfo = h.model_info || {};
        const model = modelInfo.model || h.model || h.openai_model || '';
        const provider = modelInfo.provider || h.provider || modelInfo.type || '';
        const mock = h.mock_mode === true || h.llm_mode === 'mock' || (!configured && h.status === 'ok');
        return { configured, model, provider, mock };
    }

    // ============ 渲染 ============

    function renderShell() {
        return `
        <div class="view-container view-narrow settings-view">
            <div class="view-header">
                <div class="header-eyebrow">SETTINGS</div>
                <h1>设置</h1>
                <p>系统状态、模型配置与诊断工具</p>
            </div>
            <div id="settings-content"></div>
        </div>`;
    }

    function renderContent() {
        return `
        ${renderLlmSection()}
        ${renderAppearanceSection()}
        ${renderSupportSection()}
        ${renderAccountSection()}
        ${renderDiagnosticsSection()}
        ${renderDangerSection()}`;
    }

    // --- 外观主题 ---

    function renderAppearanceSection() {
        if (!Theme) return '';
        const themes = Theme.THEMES;
        const active = state.currentTheme;
        const density = state.currentDensity;
        const accent = state.currentAccent;

        const cards = themes.map(t => {
            const isActive = t.id === active;
            const swatches = t.swatches.map(c =>
                `<span class="theme-swatch" style="background:${c}" title="${esc(c)}"></span>`
            ).join('');
            return `
            <button class="theme-card ${isActive ? 'active' : ''}" data-theme-id="${esc(t.id)}" style="--theme-accent:${t.swatches[2]}">
                <div class="theme-swatch-row">${swatches}</div>
                <div class="theme-name">
                    <span>${esc(t.name)}</span>
                    <span class="theme-check">✓</span>
                </div>
                <div class="theme-desc">${esc(t.desc)}${t.dark ? ' · 暗色' : ' · 浅色'}</div>
            </button>`;
        }).join('');

        // 主色调选择器：点击颜色圆点即时切换主色（圆点颜色随主题明暗显示对应变体）
        const accents = Theme.ACCENTS || [];
        const accentDots = accents.map(a => {
            const isActive = a.id === accent;
            const dotColor = (Theme.accentColor ? Theme.accentColor(a.id) : '') || a.color;
            return `
            <button class="accent-dot ${isActive ? 'active' : ''}" data-accent-id="${esc(a.id)}" style="--dot-color:${dotColor}" title="${esc(a.name)}">
                <span class="accent-dot-inner"></span>
            </button>`;
        }).join('');

        const accentReset = accent
            ? `<button class="accent-reset" id="btn-accent-reset" title="清除自定义主色，回归主题预设">重置</button>`
            : '';

        return `
        <div class="settings-section">
            <div class="section-title">
                <span class="title-icon">🎨</span>
                <span>外观主题</span>
                <span class="title-tag">${esc(Theme.getMeta(active).name)}</span>
            </div>
            <div class="theme-grid">${cards}</div>
            <div class="accent-picker">
                <div class="accent-label">
                    <span class="opt-label">主色调</span>
                    <span class="accent-hint">点击颜色即时切换${accent ? ' · 已自定义' : ''}</span>
                </div>
                <div class="accent-dots">${accentDots}</div>
                ${accentReset}
            </div>
            <div class="appearance-options">
                <span class="opt-label">信息密度</span>
                <button class="opt-chip ${density === 'comfortable' ? 'active' : ''}" data-density="comfortable">舒适</button>
                <button class="opt-chip ${density === 'compact' ? 'active' : ''}" data-density="compact">紧凑</button>
            </div>
        </div>`;
    }

    // --- 系统健康（诊断区内部） ---

    function renderLlmSection() {
        const h = state.health;
        const llm = getLlmInfo(h);
        const loading = state.loadingHealth || state.loadingLlmConfig;
        const cfg = state.llmConfig;

        let configRows;
        if (loading) {
            configRows = '<div class="skeleton-line" style="width:60%"></div><div class="skeleton-line" style="width:40%"></div>';
        } else {
            const statusCls = llm.configured ? 'ok' : 'warn';
            const statusText = llm.configured ? '已配置' : '未配置';
            const mockBadge = llm.mock ? '<span class="llm-mock-badge" title="系统未检测到真实 LLM 配置，正使用模拟响应">Mock 模式</span>' : '';
            configRows = `
            <div class="health-row">
                <span class="health-label"><span class="status-dot-lg ${statusCls}"></span>配置状态</span>
                <span class="health-value ${statusCls}">${esc(statusText)} ${mockBadge}</span>
            </div>
            <div class="health-row">
                <span class="health-label">编排模型</span>
                <span class="health-value">${esc(llm.model || (cfg && cfg.agent && cfg.agent.model) || '—')}</span>
            </div>
            <div class="health-row">
                <span class="health-label">提供商</span>
                <span class="health-value">${esc(llm.provider || (cfg && cfg.agent && cfg.agent.provider) || '—')}</span>
            </div>`;
        }

        // 可编辑配置表单（仅在配置加载完成后显示）
        let formHtml = '';
        if (!state.loadingLlmConfig && cfg) {
            const agent = cfg.agent || {};
            const gen = cfg.gen || {};
            const agentMasked = agent.api_key_masked || '';
            const genMasked = gen.api_key_masked || '';
            const saveStatus = state.llmSaveStatus
                ? `<span class="llm-save-status ${state.llmSaveStatus.type}">${esc(state.llmSaveStatus.text)}</span>`
                : '<span class="llm-save-status">保存后立即生效，无需重启服务</span>';

            const templates = (cfg.templates && cfg.templates.length) ? cfg.templates : [];
            const templateOptions = templates.map(t =>
                `<option value="${esc(t.id)}">${esc(t.name)}${t.default_model ? ' · ' + esc(t.default_model) : ''}</option>`
            ).join('');

            formHtml = `
            <div class="llm-config-form" style="margin-top:0.9rem;padding-top:0.9rem;border-top:1px dashed var(--line-soft);">
                ${templates.length ? `
                <div class="llm-field full llm-template-pick">
                    <label>快速选择一个服务（一键填充 Base URL 与模型）<span class="field-tag">可选</span></label>
                    <div class="llm-template-row">
                        <select id="llm-template"><option value="">— 手动配置 —</option>${templateOptions}</select>
                        <span class="llm-template-note" id="llm-template-note"></span>
                    </div>
                </div>
                <div class="llm-divider"></div>` : ''}
                <div class="llm-field full">
                    <label>编排模型（Agent）<span class="field-tag">强模型 · function calling</span></label>
                </div>
                <div class="llm-field">
                    <label>API Key</label>
                    <input type="password" id="llm-agent-key" placeholder="${agentMasked ? esc(agentMasked) + '（留空保持不变）' : 'sk-...'}" autocomplete="off" spellcheck="false">
                    <span class="field-hint">留空表示保持现有密钥不变</span>
                </div>
                <div class="llm-field">
                    <label>模型名称</label>
                    <input type="text" id="llm-agent-model" value="${esc(agent.model || '')}" placeholder="gpt-4o-mini" spellcheck="false">
                </div>
                <div class="llm-field full">
                    <label>API Base URL</label>
                    <input type="text" id="llm-agent-base" value="${esc(agent.base_url || '')}" placeholder="https://api.openai.com/v1" spellcheck="false">
                    <span class="field-hint">兼容 OpenAI 协议的服务均可，如 <code>DeepSeek</code> / <code>Qwen</code> / <code>GLM</code></span>
                </div>

                <div class="llm-field full" style="margin-top:0.4rem;">
                    <label>生成模型（内容生成）<span class="field-tag">快模型 · 可选</span></label>
                </div>
                <div class="llm-field">
                    <label>API Key</label>
                    <input type="password" id="llm-gen-key" placeholder="${genMasked ? esc(genMasked) + '（留空保持不变）' : '留空则复用编排模型'}" autocomplete="off" spellcheck="false">
                </div>
                <div class="llm-field">
                    <label>模型名称</label>
                    <input type="text" id="llm-gen-model" value="${esc(gen.model || '')}" placeholder="留空则复用编排模型" spellcheck="false">
                </div>

                <div class="llm-config-actions">
                    <button class="btn btn-primary btn-sm" id="btn-save-llm" ${state.savingLlm ? 'disabled' : ''}>
                        ${state.savingLlm ? '保存中...' : '保存配置'}
                    </button>
                    ${saveStatus}
                </div>
            </div>
            <div class="privacy-note">
                <span class="lock-ico">🔒</span>
                <span>密钥仅保存在服务端本地配置文件（<code>backend/data/</code>），不会出现在日志中，也不会通过 API 明文返回。前端始终以脱敏形式显示。</span>
            </div>`;
        }

        // 配置指引（未配置且无表单数据时显示）
        const hint = (!loading && !llm.configured && !cfg) ? `
        <div class="llm-config-hint">
            <strong>配置方法：</strong><br>
            在下方表单填入密钥与模型，或在服务端设置环境变量：<br>
            <code>AGENT_API_KEY</code> / <code>AGENT_MODEL</code> / <code>AGENT_BASE_URL</code> — 编排模型<br>
            <code>GEN_API_KEY</code> / <code>GEN_MODEL</code> / <code>GEN_BASE_URL</code> — 生成模型（可选）<br>
            或使用 Mock 模式（无需配置密钥，仅返回模拟数据，适合开发调试）。
        </div>` : '';

        return `
        <div class="settings-section">
            <div class="section-title">
                <span class="title-icon">🤖</span>
                <span>LLM 配置</span>
                ${!loading && llm.mock ? `<span class="title-tag">Mock</span>` : ''}
            </div>
            ${configRows}
            ${formHtml}
            ${hint}
            <div class="llm-test-area">
                <div class="llm-test-actions">
                    <button class="btn btn-primary btn-sm" id="btn-test-llm" ${state.testing || loading ? 'disabled' : ''}>
                        ${state.testing ? '测试中...' : '测试 LLM 连通性'}
                    </button>
                    <span style="font-size:0.78rem;color:var(--ink-faint);">发送一条测试消息，检测 LLM 是否正常响应</span>
                </div>
                <div class="llm-test-result ${state.testResult ? '' : 'empty'}" id="llm-test-result">
                    ${renderTestResult()}
                </div>
            </div>
        </div>`;
    }

    function renderTestResult() {
        if (state.testing) {
            return '<span class="spinner" style="width:16px;height:16px;border-width:2px;vertical-align:middle"></span> 正在等待 LLM 响应...';
        }
        if (!state.testResult) {
            return '点击上方按钮测试 LLM 连通性';
        }
        if (state.testResult.error) {
            return '⚠ ' + esc(state.testResult.error);
        }
        let prefix = '';
        if (state.testMockMode) {
            prefix = '【Mock 模式 — 未检测到 content_delta 事件】\n\n';
        }
        return prefix + esc(state.testResult.text);
    }

    // --- 数据统计 ---

    function renderStatsSection() {
        const s = state.stats;
        let body;
        if (state.loadingStats) {
            body = '<div class="skeleton-line" style="width:12rem"></div>';
        } else {
            body = `
            <div class="stats-grid">
                <div class="stat-cell">
                    <div class="stat-cell-label">投递总数</div>
                    <div class="stat-cell-value" data-target="${s.applications}">0</div>
                    <div class="stat-cell-sub">条记录</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-cell-label">对话会话</div>
                    <div class="stat-cell-value" data-target="${s.sessions}">0</div>
                    <div class="stat-cell-sub">个会话</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-cell-label">画像完成度</div>
                    <div class="stat-cell-value" data-target="${s.completion}" data-suffix="%">0%</div>
                    <div class="stat-cell-sub">已完成</div>
                </div>
            </div>`;
        }
        return body;
    }

    // --- 系统健康（诊断区内部） ---

    function renderHealthBody() {
        const h = state.health;
        const st = getHealthStatus(h);
        const db = getDbStatus(h);
        const version = h ? (h.version || '未知') : '—';
        const uptime = h ? formatUptime(h.uptime) : '—';
        const startedAt = h && h.started_at ? h.started_at : '';

        if (state.loadingHealth) {
            return `
            <div class="settings-loading">
                <div class="spinner"></div>
                <span>正在检查系统健康...</span>
            </div>`;
        }
        return `
        <div class="health-row">
            <span class="health-label"><span class="status-dot-lg ${st.cls}"></span>系统状态</span>
            <span class="health-value ${st.cls}">${esc(st.text)}</span>
        </div>
        <div class="health-row">
            <span class="health-label">版本</span>
            <span class="health-value">${esc(version)}</span>
        </div>
        <div class="health-row">
            <span class="health-label">运行时间</span>
            <span class="health-value">${esc(uptime)}</span>
        </div>
        ${startedAt ? `
        <div class="health-row">
            <span class="health-label">启动时间</span>
            <span class="health-value">${esc(startedAt)}</span>
        </div>` : ''}
        <div class="health-row">
            <span class="health-label"><span class="status-dot-lg ${db.cls}"></span>数据库</span>
            <span class="health-value ${db.cls}">${esc(db.text)}</span>
        </div>`;
    }

    // --- 诊断信息（健康 + 数据统计，折叠收纳） ---

    function renderDiagnosticsSection() {
        const h = state.health;
        const st = getHealthStatus(h);
        const stats = renderStatsSection();
        return `
        <div class="settings-section">
            <div class="section-title" style="cursor:pointer" id="diag-toggle" data-collapsed="1">
                <span class="title-icon">🛠</span>
                <span>系统诊断</span>
                ${h && !state.loadingHealth ? `<span class="title-tag" style="margin-left:auto;font-size:0.68rem;font-weight:500">${esc(st.text)} · 点击展开</span>` : ''}
            </div>
            <div class="diag-body" id="diag-body" style="display:none">
                <div class="diag-stats">${stats}</div>
                <div class="diag-divider"></div>
                ${renderHealthBody()}
                <div style="margin-top:0.7rem">
                    <button class="btn btn-ghost btn-sm" id="btn-refresh-health">刷新</button>
                </div>
            </div>
        </div>
        ${renderAboutSection()}`;
    }

    // --- 关于 ---

    function renderAboutSection() {
        const h = state.health;
        const version = h ? (h.version || 'dev') : 'dev';
        return `
        <div class="settings-section">
            <div class="section-title">
                <span class="title-icon">ℹ</span>
                <span>关于</span>
            </div>
            <div class="about-row">
                <span class="about-label">项目名称</span>
                <span class="about-value">${esc(PROJECT_INFO.name)}</span>
            </div>
            <div class="about-row">
                <span class="about-label">版本</span>
                <span class="about-value text-mono">${esc(version)}</span>
            </div>
            <div class="about-row">
                <span class="about-label">源代码</span>
                <span class="about-value"><a href="${esc(PROJECT_INFO.repo)}" target="_blank" rel="noopener noreferrer">GitHub 仓库 ↗</a></span>
            </div>
            <div class="about-desc">${esc(PROJECT_INFO.description)}</div>
        </div>`;
    }

    // --- 支持本项目 ---

    function renderSupportSection() {
        return `
        <div class="settings-section">
            <div class="section-title">
                <span class="title-icon">☕</span>
                <span>支持本项目</span>
                <span class="title-tag">完全免费</span>
            </div>
            <p class="support-intro">
                OfferCabin 完全免费、无广告，也没有任何付费功能。如果它在求职路上帮到了你，欢迎请作者喝杯咖啡——金额随意、纯属自愿，你的支持是这个项目持续维护的动力。
            </p>
            <div class="donate-grid">
                <div class="donate-card">
                    <img class="donate-qr" src="assets/donate/wechat.jpg" alt="微信赞赏码" loading="lazy">
                    <span class="donate-label">微信</span>
                </div>
                <div class="donate-card">
                    <img class="donate-qr" src="assets/donate/alipay.jpg" alt="支付宝收款码" loading="lazy">
                    <span class="donate-label">支付宝</span>
                </div>
            </div>
            <div class="donate-note">扫码即可 · 不影响任何功能 · 不留存任何信息</div>
        </div>`;
    }

    // --- 账号安全 ---

    function renderAccountSection() {
        const user = API.currentUser();
        return `
        <div class="settings-section">
            <div class="section-title">
                <span class="title-icon">🔐</span>
                <span>账号安全</span>
            </div>
            <div class="about-row">
                <span class="about-label">当前账号</span>
                <span class="about-value">${esc(user ? user.username : '')}</span>
            </div>
            <div class="about-row" style="flex-direction:column;align-items:flex-start;gap:0.6rem;">
                <span class="about-label" style="margin:0;">修改密码</span>
                <div style="display:flex;gap:0.5rem;flex-wrap:wrap;width:100%;">
                    <input type="password" id="pwd-old" placeholder="原密码" style="flex:1;min-width:120px;padding:8px 10px;border:1px solid var(--border, #d8d6cf);border-radius:8px;font-size:13px;background:transparent;color:inherit;">
                    <input type="password" id="pwd-new" placeholder="新密码（至少 8 位）" style="flex:1;min-width:140px;padding:8px 10px;border:1px solid var(--border, #d8d6cf);border-radius:8px;font-size:13px;background:transparent;color:inherit;">
                    <button class="btn btn-primary btn-sm" id="btn-change-password" style="white-space:nowrap;">修改密码</button>
                </div>
                <div class="msg" id="msg-change-password" style="font-size:12.5px;min-height:18px;"></div>
            </div>
        </div>`;
    }

    // --- 危险操作 ---

    function renderDangerSection() {
        return `
        <div class="settings-section danger">
            <div class="section-title">
                <span class="title-icon">⚠</span>
                <span>危险操作</span>
            </div>
            <div class="danger-item">
                <div class="danger-info">
                    <div class="danger-title">清除所有对话会话</div>
                    <div class="danger-desc">删除所有 Agent 对话记录，此操作不可撤销。</div>
                </div>
                <button class="btn btn-danger btn-sm" id="btn-clear-sessions">清除会话</button>
            </div>
            <div class="danger-item">
                <div class="danger-info">
                    <div class="danger-title">重置所有数据</div>
                    <div class="danger-desc">清空投递记录、对话会话与简历画像，恢复到初始状态。</div>
                </div>
                <button class="btn btn-danger btn-sm" id="btn-reset-data">重置数据</button>
            </div>
        </div>`;
    }

    // ============ 渲染入口 ============

    function rerender() {
        if (!root) return;
        const content = root.querySelector('#settings-content');
        if (content) {
            content.innerHTML = renderContent();
            bindDynamicEvents();
            animateStats();
        }
    }

    function animateStats() {
        if (!Motion || !Motion.countUp) return;
        const els = root.querySelectorAll('.stat-cell-value');
        els.forEach(el => {
            const target = parseFloat(el.dataset.target || '0');
            const suffix = el.dataset.suffix || '';
            Motion.countUp(el, target, { duration: 1000, suffix: suffix });
        });
    }

    // ============ 数据加载 ============

    async function loadHealth() {
        state.loadingHealth = true;
        rerender();
        try {
            const data = await API.health();
            state.health = data;
        } catch (e) {
            state.health = { status: 'error', error: e.message };
        } finally {
            state.loadingHealth = false;
            rerender();
        }
    }

    async function loadStats() {
        state.loadingStats = true;
        rerender();
        try {
            const [statsRes, sessionsRes, profileRes] = await Promise.allSettled([
                API.get('/applications/stats/overview'),
                API.get('/agent/sessions'),
                API.get('/profiles/completion'),
            ]);

            let appCount = 0;
            if (statsRes.status === 'fulfilled') {
                const s = statsRes.value;
                appCount = s.total || s.total_applications || s.count || 0;
            }

            let sessionCount = 0;
            if (sessionsRes.status === 'fulfilled') {
                const s = sessionsRes.value;
                sessionCount = Array.isArray(s) ? s.length : (s.total || s.count || (s.sessions ? s.sessions.length : 0));
            }

            let completion = 0;
            if (profileRes.status === 'fulfilled') {
                completion = profileRes.value.overall || 0;
            }

            state.stats = {
                applications: appCount,
                sessions: sessionCount,
                completion: Math.round(completion),
            };
        } catch (e) {
            // 静默失败
        } finally {
            state.loadingStats = false;
            rerender();
        }
    }

    async function loadLlmConfig() {
        state.loadingLlmConfig = true;
        rerender();
        try {
            const data = await API.get('/settings/llm');
            state.llmConfig = data;
        } catch (e) {
            // 端点不可用（旧版后端），保留 null，表单不显示
            state.llmConfig = null;
        } finally {
            state.loadingLlmConfig = false;
            rerender();
        }
    }

    async function saveLlmConfig() {
        if (state.savingLlm) return;
        const agentKeyEl = root.querySelector('#llm-agent-key');
        const agentModelEl = root.querySelector('#llm-agent-model');
        const agentBaseEl = root.querySelector('#llm-agent-base');
        const genKeyEl = root.querySelector('#llm-gen-key');
        const genModelEl = root.querySelector('#llm-gen-model');

        if (!agentModelEl) return;

        // 构造 payload：空 key 字段省略（保持不变）
        const agent = {
            model: (agentModelEl.value || '').trim(),
            base_url: (agentBaseEl.value || '').trim(),
        };
        const agentKey = (agentKeyEl.value || '').trim();
        if (agentKey) agent.api_key = agentKey;

        const gen = {
            model: (genModelEl.value || '').trim(),
            base_url: '', // gen 不单独配 base_url，复用或省略
        };
        const genKey = (genKeyEl.value || '').trim();
        if (genKey) gen.api_key = genKey;

        // 基础校验：如果填了 key 但没填 model/base_url，给出提示（非阻断）
        if (agentKey && !agent.model) {
            state.llmSaveStatus = { type: 'err', text: '请填写模型名称' };
            rerender();
            return;
        }

        state.savingLlm = true;
        state.llmSaveStatus = { type: '', text: '保存中...' };
        rerender();

        try {
            const result = await API.put('/settings/llm', { agent, gen });
            state.llmConfig = result;
            state.llmSaveStatus = { type: 'ok', text: '已保存并即时生效' };
            // 清空密码字段
            if (agentKeyEl) agentKeyEl.value = '';
            if (genKeyEl) genKeyEl.value = '';
            // 重新拉取健康状态以反映新配置
            loadHealth();
            API.toast('LLM 配置已保存', 'success');
        } catch (e) {
            state.llmSaveStatus = { type: 'err', text: '保存失败：' + (e.message || '未知错误') };
            API.toast('保存失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.savingLlm = false;
            rerender();
            // 4 秒后清除状态
            setTimeout(() => {
                state.llmSaveStatus = null;
                if (root) rerender();
            }, 4000);
        }
    }

    // ============ 主题切换 ============

    function applyTheme(themeId) {
        if (!Theme) return;
        Theme.apply(themeId);
        state.currentTheme = themeId;
        rerender();
        API.toast('主题已切换：' + (Theme.getMeta(themeId).name), 'info', 1800);
    }

    function applyDensity(d) {
        if (!Theme) return;
        Theme.applyDensity(d);
        state.currentDensity = d;
        rerender();
    }

    function setAccent(accentId) {
        if (!Theme) return;
        Theme.applyAccent(accentId);
        state.currentAccent = accentId || '';
        rerender();
        if (accentId) {
            const meta = Theme.ACCENTS.find(a => a.id === accentId);
            if (meta) API.toast('主色调已切换：' + meta.name, 'info', 1800);
        } else {
            API.toast('已重置为主题预设主色', 'info', 1800);
        }
    }

    // ============ LLM 测试 ============

    async function testLlm() {
        if (state.testing) return;
        state.testing = true;
        state.testResult = null;
        state.testMockMode = false;
        rerender();

        let contentBuffer = '';
        let hasContentDelta = false;
        let hadError = false;

        try {
            await API.stream('/agent/chat', { message: '测试' }, (evt) => {
                if (evt.type === 'content_delta') {
                    hasContentDelta = true;
                    contentBuffer += evt.delta || '';
                    // 实时更新
                    state.testResult = { text: contentBuffer };
                    updateTestResult();
                } else if (evt.type === 'done') {
                    if (!hasContentDelta && evt.content) {
                        contentBuffer = evt.content;
                        state.testResult = { text: contentBuffer };
                    }
                } else if (evt.type === 'error') {
                    hadError = true;
                    state.testResult = { error: evt.message || 'LLM 返回错误' };
                    updateTestResult();
                }
            });

            // 流结束后判定
            if (!hadError) {
                if (!hasContentDelta) {
                    // Mock 模式
                    state.testMockMode = true;
                    if (!contentBuffer) {
                        state.testResult = { text: '（未收到 content_delta 事件，疑似 Mock 模式）' };
                    }
                }
                if (!state.testResult) {
                    state.testResult = { text: contentBuffer || '（空响应）' };
                }
            }
        } catch (e) {
            state.testResult = { error: e.message || '请求失败' };
        } finally {
            state.testing = false;
            rerender();
        }
    }

    function updateTestResult() {
        const el = root.querySelector('#llm-test-result');
        if (!el) return;
        const isError = state.testResult && state.testResult.error;
        el.className = 'llm-test-result ' + (isError ? 'error' : (state.testing ? 'streaming' : ''));
        el.innerHTML = renderTestResult();
    }

    // ============ 危险操作 ============

    async function clearSessions() {
        if (!confirm('确定清除所有对话会话？此操作不可撤销。')) return;
        const btn = root.querySelector('#btn-clear-sessions');
        if (btn) { btn.disabled = true; btn.textContent = '清除中...'; }
        try {
            // 尝试批量删除端点
            await API.del('/agent/sessions');
            API.toast('已清除所有对话会话', 'success');
            await loadStats();
        } catch (e) {
            // 如果批量端点不存在，尝试逐个删除
            try {
                const sessions = await API.get('/agent/sessions');
                const list = Array.isArray(sessions) ? sessions : (sessions.sessions || []);
                if (list.length === 0) {
                    API.toast('没有需要清除的会话', 'info');
                } else {
                    let ok = 0;
                    for (const s of list) {
                        try {
                            await API.del('/agent/sessions/' + s.session_id);
                            ok++;
                        } catch (e2) { /* 忽略单个失败 */ }
                    }
                    API.toast('已清除 ' + ok + ' / ' + list.length + ' 个会话', 'success');
                }
                await loadStats();
            } catch (e2) {
                API.toast('清除会话失败: ' + (e2.message || e.message), 'error');
            }
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '清除会话'; }
        }
    }

    async function resetData() {
        if (!confirm('⚠ 警告：此操作将清空所有数据（投递记录、对话、画像），且不可撤销！\n\n确定继续？')) return;
        if (!confirm('再次确认：真的要重置所有数据吗？')) return;
        const btn = root.querySelector('#btn-reset-data');
        if (btn) { btn.disabled = true; btn.textContent = '重置中...'; }
        try {
            await API.post('/system/reset-data', {});
            API.toast('数据已重置', 'success');
            // 重新加载所有数据
            await Promise.all([loadHealth(), loadStats()]);
        } catch (e) {
            // 尝试备用端点
            try {
                await API.del('/system/reset-data');
                API.toast('数据已重置', 'success');
                await Promise.all([loadHealth(), loadStats()]);
            } catch (e2) {
                API.toast('重置失败: ' + (e2.message || e.message || '端点不可用'), 'error');
            }
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '重置数据'; }
        }
    }

    // ============ 事件绑定 ============

    function bindDynamicEvents() {
        // 预设模型模板：选择后一键填充 Agent 的 Base URL 与模型名称
        const tplSelect = root.querySelector('#llm-template');
        if (tplSelect) {
            const tplMap = {};
            ((state.llmConfig && state.llmConfig.templates) || []).forEach(t => { tplMap[t.id] = t; });
            tplSelect.addEventListener('change', () => {
                const tpl = tplMap[tplSelect.value];
                const noteEl = root.querySelector('#llm-template-note');
                if (!tpl) {
                    if (noteEl) noteEl.textContent = '';
                    return;
                }
                const base = root.querySelector('#llm-agent-base');
                const model = root.querySelector('#llm-agent-model');
                if (base) base.value = tpl.base_url || '';
                if (model && tpl.default_model) model.value = tpl.default_model;
                if (noteEl) noteEl.textContent = tpl.note || '';
            });
        }

        // 诊断信息折叠展开
        const diagToggle = root.querySelector('#diag-toggle');
        const diagBody = root.querySelector('#diag-body');
        if (diagToggle && diagBody) {
            diagToggle.addEventListener('click', () => {
                const collapsed = diagBody.style.display !== 'none';
                diagBody.style.display = collapsed ? 'none' : 'block';
                diagToggle.dataset.collapsed = collapsed ? '1' : '0';
                // 展开时统计数字回暖显
                if (!collapsed) animateStats();
            });
        }

        const refreshHealth = root.querySelector('#btn-refresh-health');
        if (refreshHealth) refreshHealth.addEventListener('click', loadHealth);

        const testBtn = root.querySelector('#btn-test-llm');
        if (testBtn) testBtn.addEventListener('click', testLlm);

        const clearBtn = root.querySelector('#btn-clear-sessions');
        if (clearBtn) clearBtn.addEventListener('click', clearSessions);

        const resetBtn = root.querySelector('#btn-reset-data');
        if (resetBtn) resetBtn.addEventListener('click', resetData);

        // 修改密码
        const changePwdBtn = root.querySelector('#btn-change-password');
        if (changePwdBtn) changePwdBtn.addEventListener('click', changePassword);

        // 主题卡片
        root.querySelectorAll('.theme-card').forEach(card => {
            card.addEventListener('click', () => {
                applyTheme(card.dataset.themeId);
            });
        });

        // 密度切换
        root.querySelectorAll('.opt-chip[data-density]').forEach(chip => {
            chip.addEventListener('click', () => {
                applyDensity(chip.dataset.density);
            });
        });

        // 主色调点击
        root.querySelectorAll('.accent-dot').forEach(dot => {
            dot.addEventListener('click', () => {
                setAccent(dot.dataset.accentId);
            });
        });
        const accentResetBtn = root.querySelector('#btn-accent-reset');
        if (accentResetBtn) accentResetBtn.addEventListener('click', () => setAccent(''));

        // LLM 配置保存
        const saveLlmBtn = root.querySelector('#btn-save-llm');
        if (saveLlmBtn) saveLlmBtn.addEventListener('click', saveLlmConfig);

        // 赞赏码点击放大
        root.querySelectorAll('.donate-qr').forEach(img => {
            img.addEventListener('click', () => openDonateModal(img.src, img.alt || ''));
        });
    }

    // ============ 赞赏码浮层 ============

    let donateModalEl = null;
    function onDonateEsc(e) {
        if (e.key === 'Escape') closeDonateModal();
    }
    function closeDonateModal() {
        if (!donateModalEl) return;
        donateModalEl.remove();
        donateModalEl = null;
        document.removeEventListener('keydown', onDonateEsc);
        document.body.style.overflow = '';
    }
    function openDonateModal(src, label) {
        if (donateModalEl) closeDonateModal();
        const overlay = document.createElement('div');
        overlay.className = 'donate-modal';
        const img = document.createElement('img');
        img.src = src;
        if (label) img.alt = label;
        overlay.appendChild(img);
        if (label) {
            const cap = document.createElement('div');
            cap.className = 'donate-modal-cap';
            cap.textContent = label;
            overlay.appendChild(cap);
        }
        overlay.addEventListener('click', closeDonateModal);
        document.body.appendChild(overlay);
        donateModalEl = overlay;
        document.body.style.overflow = 'hidden';
        document.addEventListener('keydown', onDonateEsc);
    }

    // ============ 账号安全 ============

    async function changePassword() {
        const oldPwd = root.querySelector('#pwd-old');
        const newPwd = root.querySelector('#pwd-new');
        const msg = root.querySelector('#msg-change-password');
        if (!oldPwd || !newPwd || !msg) return;
        const oldVal = oldPwd.value.trim();
        const newVal = newPwd.value;
        if (!oldVal || !newVal) {
            msg.className = 'msg error';
            msg.textContent = '请填写原密码和新密码';
            return;
        }
        if (newVal.length < 8) {
            msg.className = 'msg error';
            msg.textContent = '新密码至少 8 位';
            return;
        }
        try {
            await API.auth.changePassword(oldVal, newVal);
            oldPwd.value = '';
            newPwd.value = '';
            msg.className = 'msg success';
            msg.textContent = '密码已修改，登录状态已刷新';
        } catch (err) {
            msg.className = 'msg error';
            msg.textContent = err.message || '修改失败';
        }
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        // 初始化外观状态（从 Theme 管理器读取当前值）
        if (Theme) {
            state.currentTheme = Theme.current();
            state.currentDensity = Theme.currentDensity();
            state.currentAccent = Theme.currentAccent();
        }
        root.innerHTML = renderShell();

        // 并行加载健康状态、数据统计与 LLM 配置
        await Promise.all([loadHealth(), loadStats(), loadLlmConfig()]);
    }

    function cleanup() {
        closeDonateModal();
        root = null;
    }

    global.OfferCabinViews = global.OfferCabinViews || {};
    global.OfferCabinViews.settings = { mount, cleanup, title: '设置' };
})(window);
