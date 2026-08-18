/**
 * 智能填表视图 — Smart form auto-fill wizard with Boss login check
 * 4 步向导：提取表单 → 匹配画像 → 预览确认 → 自动填写
 * 含 Boss 登录态横幅、LLM 语义匹配开关、截图预览、控制台脚本兜底
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const Motion = global.OfferClawMotion;
    const esc = API.esc.bind(API);

    // ============ 常量 ============

    const CSS_ID = 'smart-fill-styles';

    const STEPS = [
        { num: 1, label: '提取表单' },
        { num: 2, label: '匹配画像' },
        { num: 3, label: '预览确认' },
        { num: 4, label: '自动填写' },
    ];

    const STATUS_REFRESH_INTERVAL = 30000;

    // ============ 状态 ============

    const state = {
        step: 1,
        login: { logged_in: false, anti_crawl: false, checked: false },
        url: '',
        fields: [],
        pageTitle: '',
        fieldCount: 0,
        useLLM: true,
        matches: [],
        unmatchedFields: [],
        unmatchedProfile: {},
        summary: null,
        matchDone: false,
        fillResults: null,
        generatedScript: '',
        scriptCopied: false,
        browserStatus: { browser_running: false, active_sessions: 0 },
        loading: {
            login: false,
            extract: false,
            match: false,
            fill: false,
            script: false,
            status: false,
        },
    };

    let root = null;
    let statusTimer = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.smartfill-view { padding-bottom: 5rem; }

/* --- Login banner --- */
.sf-login-banner {
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
.sf-login-banner.ok { border-color: var(--olive); background: var(--olive-soft); }
.sf-login-banner.warn { border-color: var(--warn); background: #fdf6e3; }
.sf-login-banner.err { border-color: var(--danger); background: var(--terra-soft); }
.sf-login-banner-icon {
    width: 34px; height: 34px;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.05rem; font-weight: 700;
    flex-shrink: 0;
}
.sf-login-banner.ok .sf-login-banner-icon { background: var(--olive); color: var(--paper-light); }
.sf-login-banner.warn .sf-login-banner-icon { background: var(--warn); color: var(--paper-light); }
.sf-login-banner.err .sf-login-banner-icon { background: var(--danger); color: var(--paper-light); }
.sf-login-banner-text { flex: 1; min-width: 0; }
.sf-login-banner-title { font-size: 0.86rem; font-weight: 600; color: var(--ink); margin-bottom: 0.1rem; }
.sf-login-banner-desc { font-size: 0.76rem; color: var(--ink-soft); line-height: 1.4; }
.sf-login-banner .btn { flex-shrink: 0; }

/* --- Step rail --- */
.step-rail {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-bottom: 1.6rem;
    padding: 0.9rem 1.1rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    flex-wrap: wrap;
}
.step-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    padding: 0.35rem 0.85rem 0.35rem 0.4rem;
    border-radius: 20px;
    border: 1px solid var(--line);
    background: var(--paper-light);
    color: var(--ink-soft);
    font-size: 0.82rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.25s var(--ease);
    font-family: inherit;
}
.step-pill:hover:not(.active) { border-color: var(--olive); color: var(--olive-dark); }
.step-pill .step-num {
    width: 22px; height: 22px;
    border-radius: 50%;
    background: var(--paper-deep);
    color: var(--ink-soft);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem; font-weight: 700;
    font-family: var(--font-mono);
    flex-shrink: 0;
    transition: all 0.25s var(--ease);
}
.step-pill.active {
    background: var(--olive);
    color: var(--paper-light);
    border-color: var(--olive-dark);
    box-shadow: var(--shadow-olive);
    cursor: default;
}
.step-pill.active .step-num { background: var(--paper-light); color: var(--olive-dark); }
.step-pill.done {
    background: var(--olive-soft);
    color: var(--olive-dark);
    border-color: var(--olive);
}
.step-pill.done .step-num { background: var(--olive); color: var(--paper-light); }
.step-connector {
    flex: 1;
    min-width: 20px;
    height: 1px;
    background: var(--line);
    transition: background 0.3s var(--ease);
}
.step-connector.done { background: var(--olive); }

/* --- Step panels --- */
.step-panel { animation: sfPanelIn 0.3s var(--ease-out); }
@keyframes sfPanelIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* --- URL input --- */
.sf-url-row {
    display: flex;
    gap: 0.6rem;
    align-items: center;
    flex-wrap: wrap;
}
.sf-url-input {
    flex: 1;
    min-width: 240px;
    padding: 0.6rem 0.85rem;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.9rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.sf-url-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 3px var(--olive-glow);
    background: #fff;
}

/* --- Page info strip --- */
.sf-page-info {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-top: 0.9rem;
    font-size: 0.8rem;
    color: var(--ink-soft);
    flex-wrap: wrap;
}
.sf-page-info .sf-page-title {
    font-family: var(--font-serif);
    font-weight: 600;
    color: var(--ink);
    word-break: break-all;
}
.sf-field-count {
    padding: 0.15rem 0.5rem;
    background: var(--olive-soft);
    color: var(--olive-dark);
    border-radius: 10px;
    font-size: 0.74rem;
    font-weight: 600;
    font-family: var(--font-mono);
}

/* --- Fields table --- */
.sf-fields-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
    margin-top: 0.8rem;
}
.sf-fields-table th {
    background: var(--paper-deep);
    color: var(--ink);
    font-weight: 600;
    text-align: left;
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid var(--line);
    font-size: 0.78rem;
}
.sf-fields-table td {
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid var(--line-soft);
    color: var(--ink-soft);
    vertical-align: top;
}
.sf-fields-table tr:last-child td { border-bottom: none; }
.sf-fields-table tr:hover td { background: var(--paper-light); }
.sf-field-label { color: var(--ink); font-weight: 500; }
.sf-field-selector {
    font-family: var(--font-mono);
    font-size: 0.76rem;
    color: var(--ink-faint);
    word-break: break-all;
}
.sf-type-badge {
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 4px;
    background: var(--paper-deep);
    color: var(--ink-soft);
    font-size: 0.72rem;
    font-family: var(--font-mono);
}
.sf-required-badge {
    display: inline-block;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
    background: var(--terra-soft);
    color: var(--terra-deep);
    font-size: 0.7rem;
    font-weight: 600;
}
.sf-required-badge.optional { background: var(--paper-deep); color: var(--ink-faint); }

/* --- Toggle --- */
.sf-toggle-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.9rem;
    padding: 0.7rem 0.9rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
}
.sf-toggle {
    position: relative;
    width: 38px; height: 20px;
    background: var(--line);
    border-radius: 10px;
    cursor: pointer;
    transition: background 0.2s var(--ease);
    flex-shrink: 0;
    border: none;
}
.sf-toggle.on { background: var(--olive); }
.sf-toggle::after {
    content: '';
    position: absolute;
    top: 2px; left: 2px;
    width: 16px; height: 16px;
    background: var(--paper-light);
    border-radius: 50%;
    transition: transform 0.2s var(--ease-out);
}
.sf-toggle.on::after { transform: translateX(18px); }
.sf-toggle-label { font-size: 0.84rem; color: var(--ink); font-weight: 500; }
.sf-toggle-hint { font-size: 0.74rem; color: var(--ink-faint); margin-left: auto; }

/* --- Match rows --- */
.sf-match-list { display: flex; flex-direction: column; gap: 0.5rem; }
.sf-match-row {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 0.8rem;
    align-items: center;
    padding: 0.7rem 0.9rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.sf-match-row:hover { border-color: var(--olive); box-shadow: var(--shadow-sm); }
.sf-match-field { min-width: 0; }
.sf-match-field-label {
    font-size: 0.84rem;
    color: var(--ink);
    font-weight: 500;
    margin-bottom: 0.15rem;
    word-break: break-word;
}
.sf-match-field-meta {
    font-size: 0.7rem;
    color: var(--ink-faint);
    font-family: var(--font-mono);
    word-break: break-all;
}
.sf-match-arrow {
    color: var(--olive);
    font-size: 1.1rem;
    font-weight: 700;
}
.sf-match-value-wrap { min-width: 0; }
.sf-match-value-input {
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--line);
    border-radius: 5px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.84rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.sf-match-value-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 2px var(--olive-glow);
    background: #fff;
}
.sf-match-reason {
    font-size: 0.72rem;
    color: var(--ink-faint);
    margin-top: 0.3rem;
    line-height: 1.4;
}
.sf-confidence {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.72rem;
    font-family: var(--font-mono);
    font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 10px;
    margin-top: 0.3rem;
}
.sf-confidence.high { background: var(--olive-soft); color: var(--olive-dark); }
.sf-confidence.mid { background: #fdf6e3; color: var(--warn); }
.sf-confidence.low { background: var(--terra-soft); color: var(--terra-deep); }
.sf-confidence::before {
    content: '';
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
}

/* --- Unmatched section --- */
.sf-unmatched-section {
    margin-top: 1rem;
    padding: 0.8rem 1rem;
    background: var(--terra-soft);
    border: 1px solid var(--terra);
    border-radius: 8px;
}
.sf-unmatched-title {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--terra-deep);
    margin-bottom: 0.5rem;
}
.sf-unmatched-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
}
.sf-unmatched-chip {
    font-size: 0.76rem;
    padding: 0.2rem 0.55rem;
    background: var(--card);
    border: 1px solid var(--terra);
    border-radius: 12px;
    color: var(--terra-deep);
}

/* --- Step nav --- */
.sf-step-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 1.4rem;
    padding-top: 1rem;
    border-top: 1px dashed var(--line-soft);
}
.sf-step-nav-right { display: flex; gap: 0.5rem; }

/* --- Summary --- */
.sf-summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.8rem;
    margin-bottom: 1rem;
}
.sf-summary-card {
    padding: 0.9rem 1.1rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 8px;
}
.sf-summary-card.matched { border-left: 3px solid var(--olive); }
.sf-summary-card.unmatched { border-left: 3px solid var(--terra); }
.sf-summary-num {
    font-family: var(--font-serif);
    font-size: 1.6rem;
    font-weight: 900;
    color: var(--ink);
    line-height: 1;
}
.sf-summary-card.matched .sf-summary-num { color: var(--olive-dark); }
.sf-summary-card.unmatched .sf-summary-num { color: var(--terra-deep); }
.sf-summary-label {
    font-size: 0.74rem;
    color: var(--ink-soft);
    margin-top: 0.3rem;
}

/* --- Review table --- */
.sf-review-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
}
.sf-review-table th {
    background: var(--paper-deep);
    color: var(--ink);
    font-weight: 600;
    text-align: left;
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid var(--line);
    font-size: 0.78rem;
}
.sf-review-table td {
    padding: 0.5rem 0.8rem;
    border-bottom: 1px solid var(--line-soft);
    color: var(--ink-soft);
    vertical-align: middle;
}
.sf-review-table tr:last-child td { border-bottom: none; }
.sf-review-value-input {
    width: 100%;
    padding: 0.3rem 0.5rem;
    border: 1px solid var(--line);
    border-radius: 4px;
    background: var(--paper-light);
    color: var(--ink);
    font-size: 0.8rem;
    font-family: inherit;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.sf-review-value-input:focus {
    outline: none;
    border-color: var(--olive);
    box-shadow: 0 0 0 2px var(--olive-glow);
    background: #fff;
}

/* --- Progress --- */
.sf-progress {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.9rem 1.1rem;
    background: var(--olive-soft);
    border: 1px solid var(--olive);
    border-radius: 8px;
}
.sf-progress-text {
    flex: 1;
    font-size: 0.84rem;
    color: var(--olive-dark);
    font-weight: 500;
}

/* --- Result stats --- */
.sf-result-stats {
    display: flex;
    gap: 0.8rem;
    margin-bottom: 1rem;
    flex-wrap: wrap;
}
.sf-result-stat {
    padding: 0.7rem 1rem;
    border-radius: 8px;
    border: 1px solid var(--line);
    background: var(--card);
    min-width: 120px;
}
.sf-result-stat.ok { border-left: 3px solid var(--olive); }
.sf-result-stat.fail { border-left: 3px solid var(--danger); }
.sf-result-stat-num {
    font-family: var(--font-serif);
    font-size: 1.4rem;
    font-weight: 900;
    line-height: 1;
}
.sf-result-stat.ok .sf-result-stat-num { color: var(--olive-dark); }
.sf-result-stat.fail .sf-result-stat-num { color: var(--danger); }
.sf-result-stat-label {
    font-size: 0.74rem;
    color: var(--ink-soft);
    margin-top: 0.2rem;
}

/* --- Screenshots --- */
.sf-screenshots {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    margin: 0.8rem 0;
}
.sf-screenshot {
    width: 200px;
    border: 1px solid var(--line);
    border-radius: 6px;
    overflow: hidden;
    background: var(--paper-deep);
    transition: transform 0.2s var(--ease), box-shadow 0.2s var(--ease);
}
.sf-screenshot:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.sf-screenshot img { display: block; width: 100%; height: auto; }
.sf-screenshot-label {
    padding: 0.3rem 0.5rem;
    font-size: 0.72rem;
    color: var(--ink-soft);
    background: var(--card);
    border-top: 1px solid var(--line-soft);
    font-family: var(--font-mono);
}

/* --- Result table --- */
.sf-result-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
}
.sf-result-table th {
    background: var(--paper-deep);
    color: var(--ink);
    font-weight: 600;
    text-align: left;
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid var(--line);
    font-size: 0.78rem;
}
.sf-result-table td {
    padding: 0.5rem 0.8rem;
    border-bottom: 1px solid var(--line-soft);
    color: var(--ink-soft);
    vertical-align: top;
    word-break: break-word;
}
.sf-result-table tr:last-child td { border-bottom: none; }
.sf-result-status {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-size: 0.76rem;
    font-weight: 600;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
}
.sf-result-status.ok { background: var(--olive-soft); color: var(--olive-dark); }
.sf-result-status.fail { background: var(--terra-soft); color: var(--terra-deep); }
.sf-result-status::before {
    content: '';
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
}

/* --- Script block --- */
.sf-script-block {
    margin-top: 1rem;
    background: #1e1b18;
    border-radius: 8px;
    overflow: hidden;
}
.sf-script-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.9rem;
    background: rgba(255, 255, 255, 0.05);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.sf-script-title {
    font-size: 0.74rem;
    color: #a8a299;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 1px;
}
.sf-script-copy {
    padding: 0.25rem 0.6rem;
    border: 1px solid rgba(255, 255, 255, 0.15);
    background: rgba(255, 255, 255, 0.08);
    color: #e8e4d8;
    border-radius: 4px;
    font-size: 0.74rem;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s var(--ease), color 0.15s var(--ease);
}
.sf-script-copy:hover { background: rgba(255, 255, 255, 0.15); }
.sf-script-copy.copied { color: #b8d96b; border-color: #b8d96b; }
.sf-script-block pre {
    margin: 0;
    padding: 0.9rem;
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    color: #e8e4d8;
    line-height: 1.55;
    max-height: 360px;
    white-space: pre-wrap;
    word-break: break-all;
}

/* --- Status bar --- */
.fill-status-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.6rem 1.1rem;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    margin-top: 1.5rem;
    font-size: 0.78rem;
    color: var(--ink-soft);
    box-shadow: var(--shadow-sm);
    flex-wrap: wrap;
}
.sf-status-item {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
}
.sf-status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--ink-faint);
    flex-shrink: 0;
}
.sf-status-dot.ok { background: var(--success); box-shadow: 0 0 0 3px rgba(90, 122, 58, 0.15); }
.sf-status-dot.off { background: var(--ink-faint); }
.sf-status-spacer { flex: 1; }
.sf-status-refresh {
    background: none;
    border: 1px solid var(--line);
    color: var(--ink-soft);
    padding: 0.3rem 0.6rem;
    border-radius: 5px;
    font-size: 0.74rem;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s var(--ease);
}
.sf-status-refresh:hover { border-color: var(--olive); color: var(--olive); }

/* --- Loading & empty --- */
.sf-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.7rem;
    padding: 2rem 1rem;
    color: var(--ink-faint);
    font-size: 0.84rem;
}
.sf-empty-inline {
    text-align: center;
    padding: 1.6rem 1rem;
    color: var(--ink-faint);
    font-size: 0.84rem;
    border: 1px dashed var(--line);
    border-radius: 8px;
    background: var(--paper-light);
    line-height: 1.6;
}

@media (max-width: 700px) {
    .sf-url-row { flex-direction: column; align-items: stretch; }
    .sf-match-row { grid-template-columns: 1fr; gap: 0.4rem; }
    .sf-match-arrow { transform: rotate(90deg); justify-self: start; }
    .step-rail { flex-direction: column; align-items: stretch; gap: 0.3rem; }
    .step-connector { display: none; }
    .sf-toggle-hint { display: none; }
}
`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function confidenceClass(c) {
        const v = Number(c) || 0;
        if (v >= 0.8) return 'high';
        if (v >= 0.5) return 'mid';
        return 'low';
    }

    function confidenceLabel(c) {
        const v = Number(c) || 0;
        if (v >= 0.8) return '高置信';
        if (v >= 0.5) return '中置信';
        return '低置信';
    }

    function confidencePct(c) {
        return Math.round((Number(c) || 0) * 100) + '%';
    }

    // ============ 渲染：骨架 ============

    function renderShell() {
        return `
        <div class="view-container view-narrow smartfill-view">
            <div class="view-header">
                <div class="header-eyebrow">AUTOMATION</div>
                <h1>智能填表</h1>
                <p>自动提取招聘网站表单字段，匹配你的画像并一键填写</p>
            </div>
            <div id="sf-login-banner"></div>
            <div class="step-rail" id="sf-step-rail"></div>
            <div id="sf-step-panels"></div>
            <div class="fill-status-bar" id="sf-status-bar"></div>
        </div>`;
    }

    // ============ 渲染：登录横幅 ============

    function renderLoginBanner() {
        const L = state.login;
        const checking = state.loading.login;
        let cls, icon, title, desc, showBtn, btnText;

        if (checking && !L.checked) {
            cls = ''; icon = '··'; title = '正在检查登录状态...'; desc = '请稍候';
            showBtn = false;
        } else if (L.anti_crawl) {
            cls = 'err'; icon = '!'; title = '检测到反爬限制';
            desc = 'Boss 直聘触发了反爬验证，建议稍后重试或手动登录后继续';
            showBtn = true; btnText = '重新登录';
        } else if (L.logged_in) {
            cls = 'ok'; icon = '✓'; title = 'Boss 直聘已登录';
            desc = '可正常使用自动化填表功能';
            showBtn = false;
        } else {
            cls = 'warn'; icon = '!'; title = 'Boss 直聘未登录';
            desc = '登录后可使用真实数据填表，未登录可能无法访问目标页面';
            showBtn = true; btnText = '打开登录';
        }

        return `
        <div class="sf-login-banner ${cls}">
            <div class="sf-login-banner-icon">${icon}</div>
            <div class="sf-login-banner-text">
                <div class="sf-login-banner-title">${esc(title)}</div>
                <div class="sf-login-banner-desc">${esc(desc)}</div>
            </div>
            ${showBtn ? `<button class="btn btn-primary btn-sm" id="sf-open-login">${esc(btnText)}</button>` : ''}
            <button class="btn btn-ghost btn-sm" id="sf-refresh-login" title="重新检查登录状态">刷新</button>
        </div>`;
    }

    // ============ 渲染：步骤导航条 ============

    function renderStepRail() {
        const cur = state.step;
        let html = '';
        STEPS.forEach((s, i) => {
            const isDone = s.num < cur;
            const isActive = s.num === cur;
            const cls = isActive ? 'active' : (isDone ? 'done' : '');
            html += `
            <div class="step-pill ${cls}" data-step="${s.num}">
                <span class="step-num">${isDone ? '✓' : s.num}</span>
                <span class="step-label">${esc(s.label)}</span>
            </div>`;
            if (i < STEPS.length - 1) {
                html += `<div class="step-connector ${s.num < cur ? 'done' : ''}"></div>`;
            }
        });
        return html;
    }

    // ============ 渲染：Step 1 — 提取表单 ============

    function renderStep1() {
        const loading = state.loading.extract;
        const fields = state.fields;
        const hasFields = fields.length > 0;

        let fieldsHtml = '';
        if (loading) {
            fieldsHtml = `<div class="sf-loading"><div class="spinner"></div><span>正在提取表单字段...</span></div>`;
        } else if (hasFields) {
            fieldsHtml = `
            <div class="sf-page-info">
                ${state.pageTitle ? `<span>页面：</span><span class="sf-page-title">${esc(state.pageTitle)}</span>` : ''}
                <span class="sf-field-count">${state.fieldCount || fields.length} 个字段</span>
            </div>
            <table class="sf-fields-table">
                <thead>
                    <tr>
                        <th>字段标签</th>
                        <th>类型</th>
                        <th>选择器</th>
                        <th>必填</th>
                    </tr>
                </thead>
                <tbody>
                    ${fields.map(f => `
                        <tr>
                            <td class="sf-field-label">${esc(f.label || '(无标签)')}</td>
                            <td><span class="sf-type-badge">${esc(f.type || 'unknown')}</span></td>
                            <td><span class="sf-field-selector">${esc(f.selector || '')}</span></td>
                            <td>${f.required
                                ? `<span class="sf-required-badge">必填</span>`
                                : `<span class="sf-required-badge optional">可选</span>`}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
        } else {
            fieldsHtml = `<div class="sf-empty-inline">输入招聘网站的岗位页面链接，点击"提取表单字段"开始</div>`;
        }

        const canNext = hasFields && !loading;

        return `
        <div class="step-panel" id="step-1">
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">Step 1 · 提取表单字段</h2>
                </div>
                <div class="sf-url-row">
                    <input type="url" class="sf-url-input" id="sf-url"
                        placeholder="https://www.zhipin.com/job/xxx"
                        value="${esc(state.url)}">
                    <button class="btn btn-primary" id="sf-extract-btn" ${loading ? 'disabled' : ''}>
                        ${loading ? '提取中...' : '提取表单字段'}
                    </button>
                </div>
                ${fieldsHtml}
            </div>
            <div class="sf-step-nav">
                <span></span>
                <div class="sf-step-nav-right">
                    <button class="btn btn-primary" id="sf-next-1" ${canNext ? '' : 'disabled'}>下一步 →</button>
                </div>
            </div>
        </div>`;
    }

    // ============ 渲染：Step 2 — 匹配画像 ============

    function renderStep2() {
        const loading = state.loading.match;
        const matches = state.matches;
        const unmatched = state.unmatchedFields;
        const matchDone = state.matchDone;

        let bodyHtml = '';
        if (loading) {
            bodyHtml = `<div class="sf-loading"><div class="spinner"></div><span>正在匹配画像字段...</span></div>`;
        } else if (matchDone && matches.length === 0 && unmatched.length === 0) {
            bodyHtml = `<div class="sf-empty-inline">未找到任何可匹配字段</div>`;
        } else if (matchDone) {
            bodyHtml = `<div class="sf-match-list">` + matches.map((m, i) => `
                <div class="sf-match-row" data-idx="${i}">
                    <div class="sf-match-field">
                        <div class="sf-match-field-label">${esc(m.field_label || '(未命名字段)')}</div>
                        <div class="sf-match-field-meta">${esc(m.field_selector || '')}</div>
                        <span class="sf-confidence ${confidenceClass(m.confidence)}">
                            ${confidenceLabel(m.confidence)} · ${confidencePct(m.confidence)}
                        </span>
                    </div>
                    <div class="sf-match-arrow">→</div>
                    <div class="sf-match-value-wrap">
                        <input type="text" class="sf-match-value-input" data-idx="${i}"
                            value="${esc(m.profile_value ?? '')}"
                            placeholder="（未匹配到值）">
                        ${m.reason ? `<div class="sf-match-reason">${esc(m.reason)}</div>` : ''}
                    </div>
                </div>
            `).join('') + `</div>`;

            if (unmatched.length > 0) {
                bodyHtml += `
                <div class="sf-unmatched-section">
                    <div class="sf-unmatched-title">未匹配的字段 (${unmatched.length})</div>
                    <div class="sf-unmatched-list">
                        ${unmatched.map(f => `<span class="sf-unmatched-chip">${esc(f.label || f.selector || '未知字段')}</span>`).join('')}
                    </div>
                </div>`;
            }
        } else {
            bodyHtml = `<div class="sf-empty-inline">点击"开始匹配"，将根据你的画像自动填写对应字段</div>`;
        }

        const canNext = matchDone && !loading;

        return `
        <div class="step-panel" id="step-2">
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">Step 2 · 匹配画像</h2>
                </div>
                <div class="sf-toggle-row">
                    <button class="sf-toggle ${state.useLLM ? 'on' : ''}" id="sf-llm-toggle" role="switch" aria-checked="${state.useLLM}" aria-label="使用 LLM 语义匹配"></button>
                    <span class="sf-toggle-label">使用 LLM 语义匹配</span>
                    <span class="sf-toggle-hint">关闭后仅使用规则匹配，速度更快但准确率较低</span>
                </div>
                <button class="btn btn-primary" id="sf-match-btn" ${loading ? 'disabled' : ''}>
                    ${loading ? '匹配中...' : (matchDone ? '重新匹配' : '开始匹配')}
                </button>
                <div style="margin-top:1rem">${bodyHtml}</div>
            </div>
            <div class="sf-step-nav">
                <button class="btn btn-ghost" id="sf-prev-2">← 上一步</button>
                <div class="sf-step-nav-right">
                    <button class="btn btn-primary" id="sf-next-2" ${canNext ? '' : 'disabled'}>下一步 →</button>
                </div>
            </div>
        </div>`;
    }

    // ============ 渲染：Step 3 — 预览确认 ============

    function renderStep3() {
        const matches = state.matches;
        const matchedCount = matches.length;
        const unmatchedCount = state.unmatchedFields.length;

        let tableHtml = '';
        if (matchedCount === 0) {
            tableHtml = `<div class="sf-empty-inline">没有可确认的匹配项，请返回上一步重新匹配</div>`;
        } else {
            tableHtml = `
            <table class="sf-review-table">
                <thead>
                    <tr>
                        <th>字段</th>
                        <th>填写值</th>
                        <th>置信度</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${matches.map((m, i) => `
                        <tr data-idx="${i}">
                            <td>
                                <div style="color:var(--ink);font-weight:500">${esc(m.field_label || '(未命名)')}</div>
                                <div style="font-size:0.7rem;color:var(--ink-faint);font-family:var(--font-mono);margin-top:0.15rem">${esc(m.field_selector || '')}</div>
                            </td>
                            <td>
                                <input type="text" class="sf-review-value-input" data-idx="${i}"
                                    value="${esc(m.profile_value ?? '')}">
                            </td>
                            <td>
                                <span class="sf-confidence ${confidenceClass(m.confidence)}">${confidencePct(m.confidence)}</span>
                            </td>
                            <td>
                                <button class="btn btn-danger btn-sm" data-action="remove-match" data-idx="${i}">移除</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
        }

        const canFill = matchedCount > 0;

        return `
        <div class="step-panel" id="step-3">
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">Step 3 · 预览确认</h2>
                </div>
                <div class="sf-summary">
                    <div class="sf-summary-card matched">
                        <div class="sf-summary-num">${matchedCount}</div>
                        <div class="sf-summary-label">个字段已匹配</div>
                    </div>
                    <div class="sf-summary-card unmatched">
                        <div class="sf-summary-num">${unmatchedCount}</div>
                        <div class="sf-summary-label">个字段未匹配</div>
                    </div>
                </div>
                <p style="font-size:0.8rem;color:var(--ink-soft);margin-bottom:0.8rem">
                    可直接编辑填写值，或移除不需要填写的字段。
                </p>
                ${tableHtml}
            </div>
            <div class="sf-step-nav">
                <button class="btn btn-ghost" id="sf-prev-3">← 上一步</button>
                <div class="sf-step-nav-right">
                    <button class="btn btn-primary" id="sf-start-fill" ${canFill ? '' : 'disabled'}>开始填写 →</button>
                </div>
            </div>
        </div>`;
    }

    // ============ 渲染：Step 4 — 自动填写 ============

    function renderStep4() {
        const loading = state.loading.fill;
        const results = state.fillResults;
        const scriptLoading = state.loading.script;
        const script = state.generatedScript;

        let bodyHtml = '';

        if (loading) {
            bodyHtml = `
            <div class="sf-progress">
                <div class="spinner"></div>
                <div class="sf-progress-text">正在自动填写表单字段，请稍候...</div>
            </div>`;
        } else if (results) {
            const okCount = results.success_count || 0;
            const failCount = results.fail_count || 0;
            const shots = Array.isArray(results.screenshots) ? results.screenshots : [];
            const resultList = Array.isArray(results.results) ? results.results : [];

            bodyHtml = `
            <div class="sf-result-stats">
                <div class="sf-result-stat ok">
                    <div class="sf-result-stat-num">${okCount}</div>
                    <div class="sf-result-stat-label">填写成功</div>
                </div>
                <div class="sf-result-stat fail">
                    <div class="sf-result-stat-num">${failCount}</div>
                    <div class="sf-result-stat-label">填写失败</div>
                </div>
            </div>`;

            if (shots.length > 0) {
                bodyHtml += `
                <div style="font-size:0.82rem;color:var(--ink-soft);margin-bottom:0.4rem">截图预览</div>
                <div class="sf-screenshots">
                    ${shots.map((s, i) => `
                        <div class="sf-screenshot">
                            <img src="data:image/png;base64,${esc(s)}" alt="截图 ${i + 1}">
                            <div class="sf-screenshot-label">截图 #${i + 1}</div>
                        </div>
                    `).join('')}
                </div>`;
            }

            if (resultList.length > 0) {
                bodyHtml += `
                <table class="sf-result-table">
                    <thead>
                        <tr>
                            <th>选择器</th>
                            <th>状态</th>
                            <th>填写值</th>
                            <th>错误</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${resultList.map(r => `
                            <tr>
                                <td><span class="sf-field-selector">${esc(r.selector || '')}</span></td>
                                <td><span class="sf-result-status ${r.success ? 'ok' : 'fail'}">${r.success ? '成功' : '失败'}</span></td>
                                <td>${esc(r.value ?? '')}</td>
                                <td>${r.error ? `<span style="color:var(--danger);font-size:0.78rem">${esc(r.error)}</span>` : '<span style="color:var(--ink-faint)">—</span>'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>`;
            }
        } else {
            bodyHtml = `<div class="sf-empty-inline">点击"执行自动填写"按钮开始填写表单</div>`;
        }

        let scriptHtml = '';
        if (script) {
            scriptHtml = `
            <div class="sf-script-block">
                <div class="sf-script-head">
                    <span class="sf-script-title">console script · javascript</span>
                    <button class="sf-script-copy ${state.scriptCopied ? 'copied' : ''}" id="sf-copy-script">
                        ${state.scriptCopied ? '已复制 ✓' : '复制脚本'}
                    </button>
                </div>
                <pre>${esc(script)}</pre>
            </div>`;
        }

        return `
        <div class="step-panel" id="step-4">
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">Step 4 · 自动填写</h2>
                </div>
                <button class="btn btn-primary" id="sf-run-fill" ${loading ? 'disabled' : ''}>
                    ${loading ? '填写中...' : (results ? '重新填写' : '执行自动填写')}
                </button>
                <div style="margin-top:1rem">${bodyHtml}</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">备用方案 · 控制台脚本</h2>
                </div>
                <p style="font-size:0.82rem;color:var(--ink-soft);margin-bottom:0.8rem;line-height:1.6">
                    若自动填写失败，可生成一段 JavaScript 脚本，复制后在浏览器控制台粘贴执行。
                </p>
                <button class="btn btn-ghost" id="sf-gen-script" ${scriptLoading ? 'disabled' : ''}>
                    ${scriptLoading ? '生成中...' : '生成控制台脚本'}
                </button>
                ${scriptHtml}
            </div>
            <div class="sf-step-nav">
                <button class="btn btn-ghost" id="sf-restart">重新开始</button>
                <div class="sf-step-nav-right"></div>
            </div>
        </div>`;
    }

    // ============ 渲染：状态栏 ============

    function renderStatusBar() {
        const s = state.browserStatus;
        const running = !!s.browser_running;
        const sessions = s.active_sessions || 0;
        return `
        <div class="sf-status-item">
            <span class="sf-status-dot ${running ? 'ok' : 'off'}"></span>
            <span>浏览器：${running ? '运行中' : '未运行'}</span>
        </div>
        <div class="sf-status-item">
            <span>活动会话：${sessions}</span>
        </div>
        <div class="sf-status-spacer"></div>
        <button class="sf-status-refresh" id="sf-refresh-status">刷新状态</button>`;
    }

    // ============ 渲染：分发 ============

    function renderStepPanels() {
        switch (state.step) {
            case 1: return renderStep1();
            case 2: return renderStep2();
            case 3: return renderStep3();
            case 4: return renderStep4();
            default: return renderStep1();
        }
    }

    function rerenderAll() {
        if (!root) return;
        const banner = root.querySelector('#sf-login-banner');
        if (banner) banner.innerHTML = renderLoginBanner();
        const rail = root.querySelector('#sf-step-rail');
        if (rail) rail.innerHTML = renderStepRail();
        const panels = root.querySelector('#sf-step-panels');
        if (panels) panels.innerHTML = renderStepPanels();
        const bar = root.querySelector('#sf-status-bar');
        if (bar) bar.innerHTML = renderStatusBar();
        bindAllDynamicEvents();
        if (Motion && Motion.revealOnScroll) Motion.revealOnScroll();
    }

    function rerenderBanner() {
        if (!root) return;
        const banner = root.querySelector('#sf-login-banner');
        if (banner) banner.innerHTML = renderLoginBanner();
        bindLoginEvents();
    }

    function rerenderStatus() {
        if (!root) return;
        const bar = root.querySelector('#sf-status-bar');
        if (bar) bar.innerHTML = renderStatusBar();
        bindStatusEvents();
    }

    function rerenderRailAndPanel() {
        if (!root) return;
        const rail = root.querySelector('#sf-step-rail');
        if (rail) rail.innerHTML = renderStepRail();
        const panels = root.querySelector('#sf-step-panels');
        if (panels) {
            panels.innerHTML = renderStepPanels();
            bindPanelEvents();
            const panel = panels.querySelector('.step-panel');
            if (panel && Motion && Motion.tabEnter) Motion.tabEnter(panel);
        }
    }

    function rerenderPanelOnly() {
        if (!root) return;
        const panels = root.querySelector('#sf-step-panels');
        if (panels) {
            panels.innerHTML = renderStepPanels();
            bindPanelEvents();
            const panel = panels.querySelector('.step-panel');
            if (panel && Motion && Motion.tabEnter) Motion.tabEnter(panel);
        }
    }

    // ============ 数据加载 ============

    async function checkLogin() {
        state.loading.login = true;
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
            state.loading.login = false;
            rerenderBanner();
        }
    }

    async function openLogin() {
        API.toast('正在打开登录页面，请在弹出的浏览器中完成登录...', 'info', 4000);
        try {
            await API.post('/automation/open-login', { site: 'boss', headless: false });
            API.toast('登录页已打开，完成后请点击"刷新"重新检查', 'success', 4000);
            setTimeout(() => checkLogin(), 3000);
        } catch (e) {
            API.toast('打开登录页失败: ' + (e.message || '未知错误'), 'error');
        }
    }

    async function loadStatus() {
        try {
            const data = await API.get('/automation/status');
            state.browserStatus = {
                browser_running: !!data.browser_running,
                active_sessions: data.active_sessions || 0,
            };
        } catch (e) {
            state.browserStatus = { browser_running: false, active_sessions: 0 };
        } finally {
            rerenderStatus();
        }
    }

    // ============ 业务操作 ============

    async function extractFields() {
        const urlEl = root.querySelector('#sf-url');
        const url = urlEl ? urlEl.value.trim() : '';
        if (!url) {
            API.toast('请输入岗位页面 URL', 'warn');
            return;
        }
        if (!/^https?:\/\//i.test(url)) {
            API.toast('URL 需以 http:// 或 https:// 开头', 'warn');
            return;
        }
        state.url = url;
        state.loading.extract = true;
        state.fields = [];
        state.pageTitle = '';
        state.fieldCount = 0;
        state.matchDone = false;
        state.matches = [];
        state.unmatchedFields = [];
        state.fillResults = null;
        state.generatedScript = '';
        state.scriptCopied = false;
        rerenderPanelOnly();

        try {
            const data = await API.post('/automation/extract-from-url', { url });
            state.fields = Array.isArray(data.fields) ? data.fields : [];
            state.pageTitle = data.page_title || '';
            state.fieldCount = data.field_count || state.fields.length;
            API.toast('已提取 ' + state.fields.length + ' 个字段', 'success');
        } catch (e) {
            API.toast('提取失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.loading.extract = false;
            rerenderPanelOnly();
        }
    }

    async function matchProfile() {
        if (state.fields.length === 0) {
            API.toast('请先提取表单字段', 'warn');
            return;
        }
        state.loading.match = true;
        state.matchDone = false;
        state.matches = [];
        state.unmatchedFields = [];
        state.fillResults = null;
        rerenderPanelOnly();

        try {
            const data = await API.post('/automation/match', {
                fields: state.fields,
                use_llm: state.useLLM,
            });
            state.matches = Array.isArray(data.matches) ? data.matches : [];
            state.unmatchedFields = Array.isArray(data.unmatched_fields) ? data.unmatched_fields : [];
            state.unmatchedProfile = data.unmatched_profile || {};
            state.summary = data.summary || null;
            state.matchDone = true;
            API.toast('匹配完成：' + state.matches.length + ' 个字段已匹配', 'success');
        } catch (e) {
            API.toast('匹配失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.loading.match = false;
            rerenderPanelOnly();
        }
    }

    async function autoFill() {
        if (state.matches.length === 0) {
            API.toast('没有可填写的匹配项', 'warn');
            return;
        }
        state.loading.fill = true;
        state.fillResults = null;
        rerenderPanelOnly();

        try {
            const data = await API.post('/automation/auto-fill', {
                url: state.url,
                matches: state.matches,
                profile: {},
            });
            state.fillResults = {
                results: Array.isArray(data.results) ? data.results : [],
                screenshots: Array.isArray(data.screenshots) ? data.screenshots : [],
                success_count: data.success_count || 0,
                fail_count: data.fail_count || 0,
            };
            const ok = state.fillResults.success_count;
            const fail = state.fillResults.fail_count;
            API.toast('填写完成：成功 ' + ok + ' 个，失败 ' + fail + ' 个', fail > 0 ? 'warn' : 'success', 4000);
        } catch (e) {
            API.toast('填写失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.loading.fill = false;
            rerenderPanelOnly();
        }
    }

    async function generateScript() {
        if (state.matches.length === 0) {
            API.toast('没有匹配项，无法生成脚本', 'warn');
            return;
        }
        state.loading.script = true;
        state.scriptCopied = false;
        rerenderPanelOnly();

        try {
            const data = await API.post('/automation/generate-script', {
                matches: state.matches,
                profile: {},
            });
            state.generatedScript = data.script || '';
            if (state.generatedScript) {
                API.toast('脚本已生成', 'success');
            } else {
                API.toast('返回的脚本为空', 'warn');
            }
        } catch (e) {
            API.toast('生成脚本失败: ' + (e.message || '未知错误'), 'error');
        } finally {
            state.loading.script = false;
            rerenderPanelOnly();
        }
    }

    async function copyScript() {
        if (!state.generatedScript) return;
        try {
            await navigator.clipboard.writeText(state.generatedScript);
            state.scriptCopied = true;
            API.toast('脚本已复制到剪贴板', 'success');
        } catch (e) {
            const ta = document.createElement('textarea');
            ta.value = state.generatedScript;
            document.body.appendChild(ta);
            ta.select();
            try {
                document.execCommand('copy');
                state.scriptCopied = true;
                API.toast('脚本已复制到剪贴板', 'success');
            } catch (e2) {
                API.toast('复制失败，请手动选择脚本文本', 'error');
            }
            ta.remove();
        }
        // 仅更新脚本区块，避免全量重渲染
        const copyBtn = root.querySelector('#sf-copy-script');
        if (copyBtn) {
            copyBtn.classList.add('copied');
            copyBtn.textContent = '已复制 ✓';
        }
    }

    // ============ 状态机 ============

    function goToStep(n) {
        if (n < 1 || n > 4) return;
        if (n > state.step) {
            if (state.fields.length === 0 && n > 1) {
                API.toast('请先提取表单字段', 'warn');
                return;
            }
            if (!state.matchDone && n > 2) {
                API.toast('请先完成匹配', 'warn');
                return;
            }
            if (state.matches.length === 0 && n > 3) {
                API.toast('没有可填写的匹配项', 'warn');
                return;
            }
        }
        state.step = n;
        rerenderRailAndPanel();
    }

    function resetWizard() {
        state.step = 1;
        state.url = '';
        state.fields = [];
        state.pageTitle = '';
        state.fieldCount = 0;
        state.useLLM = true;
        state.matches = [];
        state.unmatchedFields = [];
        state.unmatchedProfile = {};
        state.summary = null;
        state.matchDone = false;
        state.fillResults = null;
        state.generatedScript = '';
        state.scriptCopied = false;
        rerenderAll();
        API.toast('已重置向导', 'info', 1500);
    }

    function removeMatch(idx) {
        if (isNaN(idx) || !state.matches[idx]) return;
        const removed = state.matches.splice(idx, 1)[0];
        if (removed) {
            state.unmatchedFields.push({
                label: removed.field_label,
                selector: removed.field_selector,
                type: '',
                required: false,
                options: [],
                value: '',
            });
        }
        rerenderPanelOnly();
        API.toast('已移除该匹配项', 'info', 1500);
    }

    // ============ 事件绑定 ============

    function bindLoginEvents() {
        const loginBtn = root.querySelector('#sf-open-login');
        if (loginBtn) loginBtn.addEventListener('click', openLogin);
        const refreshBtn = root.querySelector('#sf-refresh-login');
        if (refreshBtn) refreshBtn.addEventListener('click', checkLogin);
    }

    function bindStatusEvents() {
        const refreshBtn = root.querySelector('#sf-refresh-status');
        if (refreshBtn) refreshBtn.addEventListener('click', loadStatus);
    }

    function bindPanelEvents() {
        // Step 1
        const extractBtn = root.querySelector('#sf-extract-btn');
        if (extractBtn) extractBtn.addEventListener('click', extractFields);
        const urlEl = root.querySelector('#sf-url');
        if (urlEl) {
            urlEl.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); extractFields(); }
            });
            urlEl.addEventListener('input', (e) => { state.url = e.target.value; });
        }
        const next1 = root.querySelector('#sf-next-1');
        if (next1) next1.addEventListener('click', () => goToStep(2));

        // Step 2
        const llmToggle = root.querySelector('#sf-llm-toggle');
        if (llmToggle) {
            llmToggle.addEventListener('click', () => {
                state.useLLM = !state.useLLM;
                llmToggle.classList.toggle('on', state.useLLM);
                llmToggle.setAttribute('aria-checked', String(state.useLLM));
            });
        }
        const matchBtn = root.querySelector('#sf-match-btn');
        if (matchBtn) matchBtn.addEventListener('click', matchProfile);
        const prev2 = root.querySelector('#sf-prev-2');
        if (prev2) prev2.addEventListener('click', () => goToStep(1));
        const next2 = root.querySelector('#sf-next-2');
        if (next2) next2.addEventListener('click', () => goToStep(3));

        // Inline edit match values (Step 2)
        root.querySelectorAll('.sf-match-value-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const idx = parseInt(e.target.dataset.idx, 10);
                if (state.matches[idx]) state.matches[idx].profile_value = e.target.value;
            });
        });

        // Step 3
        const prev3 = root.querySelector('#sf-prev-3');
        if (prev3) prev3.addEventListener('click', () => goToStep(2));
        const startFill = root.querySelector('#sf-start-fill');
        if (startFill) startFill.addEventListener('click', () => goToStep(4));

        root.querySelectorAll('.sf-review-value-input').forEach(input => {
            input.addEventListener('input', (e) => {
                const idx = parseInt(e.target.dataset.idx, 10);
                if (state.matches[idx]) state.matches[idx].profile_value = e.target.value;
            });
        });

        root.querySelectorAll('[data-action="remove-match"]').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.idx, 10);
                removeMatch(idx);
            });
        });

        // Step 4
        const runFill = root.querySelector('#sf-run-fill');
        if (runFill) runFill.addEventListener('click', autoFill);
        const genScript = root.querySelector('#sf-gen-script');
        if (genScript) genScript.addEventListener('click', generateScript);
        const copyScriptBtn = root.querySelector('#sf-copy-script');
        if (copyScriptBtn) copyScriptBtn.addEventListener('click', copyScript);
        const restart = root.querySelector('#sf-restart');
        if (restart) restart.addEventListener('click', resetWizard);
    }

    function bindStepRailEvents() {
        const rail = root.querySelector('#sf-step-rail');
        if (!rail) return;
        rail.addEventListener('click', (e) => {
            const pill = e.target.closest('.step-pill');
            if (!pill) return;
            const n = parseInt(pill.dataset.step, 10);
            if (n && n !== state.step) goToStep(n);
        });
    }

    function bindAllDynamicEvents() {
        bindLoginEvents();
        bindStatusEvents();
        bindPanelEvents();
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        root.innerHTML = renderShell();
        bindStepRailEvents();
        rerenderAll();
        // 并行加载登录态 + 浏览器状态
        await Promise.all([checkLogin(), loadStatus()]);
        // 定时刷新浏览器状态
        statusTimer = setInterval(loadStatus, STATUS_REFRESH_INTERVAL);
    }

    function cleanup() {
        if (statusTimer) {
            clearInterval(statusTimer);
            statusTimer = null;
        }
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.smartFill = { mount, cleanup, title: '智能填表' };
})(window);