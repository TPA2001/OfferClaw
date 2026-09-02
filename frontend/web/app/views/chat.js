/**
 * AI 求职助手视图 — "求职教练文书台"
 *
 * 风格：编辑文书台（editorial-stationery）—— 暖纸质感 + serif 标题 + mono 工具活动，与项目 paper 主题一脉相承。
 *
 * 通过 SSE 消费 /api/v1/agent/chat 的事件流，渲染：
 *   - content_delta  助手流式文本（Markdown）
 *   - tool_call_start / tool_result  工具活动卡
 *   - confirm_required  敏感操作确认卡（调 /agent/confirm 恢复）
 *   - navigate  引导跳转到其他功能视图
 *   - done / error
 *
 * 左侧会话栏：新建对话、历史会话切换、删除；右侧主对话区 + 底部输入。
 */
(function (global) {
    'use strict';

    const API = global.OfferCabinAPI;
    const Motion = global.OfferCabinMotion;
    const Router = global.OfferCabinRouter;
    const MD = global.OfferCabinMarkdown;
    const esc = API.esc.bind(API);

    // ============ 状态 ============

    const state = {
        sessions: [],           // 会话列表
        currentId: null,        // 当前会话 id（null = 新对话）
        currentTitle: '',
        thinking: false,        // 是否正在流式输出
        abort: null,            // 当前流式 AbortController
        pinnedBottom: true,     // 是否锁定在底部（用户上翻则解除）
        railCollapsed: false,   // 桌面端会话栏是否折叠
        llmStatus: null,        // LLM 配置状态（来自 /api/v1/settings/llm）
    };

    let root = null;
    let msgSeq = 0;             // 消息唯一序号，用于定位流式占位

    // SSE 事件类型分组（用于工具识别图标）
    const TOOL_ICONS = {
        get_profile: '🪪', update_profile: '🪪', update_user_preference: '🧠',
        create_application: '📥', update_application: '✏️', query_applications: '📋',
        delete_application: '🗑️', get_followups: '⏰', search_applications: '🔎',
        get_dashboard_stats: '📊', get_timeline_stats: '📈', get_company_stats: '🏢',
        get_application_advice: '💡', navigate_view: '🧭',
        extract_job_description: '📄', score_job_match: '📏', generate_resume: '📝',
        generate_cover_letter: '💌', prepare_interview: '🎤', verify_job_authenticity: '🛡️',
        evaluate_job: '⚖️', research_company: '🏛️', generate_interview_questions: '❓',
        evaluate_interview_answer: '🏅', review_interview: '📓', create_journal_entry: '✍️',
        generate_weekly_summary: '🗓️',
    };
    const TOOL_NAMES = {
        get_profile: '读取画像', update_profile: '更新画像', update_user_preference: '记录偏好',
        create_application: '创建投递', update_application: '更新投递', query_applications: '查询投递',
        delete_application: '删除投递', get_followups: '跟进提醒', search_applications: '搜索投递',
        get_dashboard_stats: '看板统计', get_timeline_stats: '投递趋势', get_company_stats: '公司统计',
        get_application_advice: '投递策略', navigate_view: '跳转视图',
        extract_job_description: '解析 JD', score_job_match: '匹配评分', generate_resume: '生成简历',
        generate_cover_letter: '生成求职信', prepare_interview: '面试准备', verify_job_authenticity: '真实性核验',
        evaluate_job: '综合评估', research_company: '公司调研', generate_interview_questions: '生成面试题',
        evaluate_interview_answer: '评估回答', review_interview: '面试复盘', create_journal_entry: '记求职日志',
        generate_weekly_summary: '生成周报', navigate_view: '视图导航',
    };

    // 快捷指令 —— 空态建议
    const SUGGESTIONS = [
        { icon: '🧭', label: '评估这个机会值不值得投', q: '帮我评估这个岗位靠不靠谱、值不值得投' },
        { icon: '📊', label: '看看我的投递进展', q: '帮我看看我现在的投递进展和数据复盘' },
        { icon: '📝', label: '根据我的画像改写简历', q: '根据我的简历画像和个人信息生成一版针对后端岗的简历' },
        { icon: '🎤', label: '为面试做准备', q: '我要准备后端技术面试，帮我生成面试题并准备要点' },
    ];

    // ============ CSS ============

    const CSS_ID = 'chat-styles';

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
/* ===== 布局：左会话栏 + 右对话区 ===== */
.ch-app { height: 100%; display: grid; grid-template-columns: 292px 1fr; overflow: hidden; }
/* 遮罩层：绝对定位脱离 grid 文档流，避免在桌面端被当作第三个网格单元把右区挤到次行 */
.ch-rail-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.25); z-index: 15; display: none; }
.ch-rail-backdrop.open { display: block; }

/* ---- 左会话栏 ---- */
.ch-rail {
    background: var(--card);
    border-right: 1px solid var(--line);
    display: flex; flex-direction: column; min-height: 0;
}
.ch-rail-head {
    padding: 0.9rem 0.9rem 0.7rem; border-bottom: 1px dashed var(--line-soft);
}
.ch-rail-eyebrow {
    font-family: var(--font-mono); font-size: 0.62rem; letter-spacing: 2px;
    color: var(--ink-faint); text-transform: uppercase; margin-bottom: 0.5rem;
}
.ch-new-btn {
    width: 100%; display: flex; align-items: center; justify-content: center; gap: 0.45rem;
    padding: 0.55rem; font-size: 0.82rem; font-weight: 600; color: var(--olive-dark);
    background: var(--olive-soft); border: 1px solid color-mix(in srgb, var(--olive) 28%, transparent);
    border-radius: 8px; cursor: pointer; transition: all 0.2s var(--ease);
}
.ch-new-btn:hover { background: color-mix(in srgb, var(--olive) 18%, var(--paper-light)); transform: translateY(-1px); }
.ch-rail-list { flex: 1; overflow-y: auto; padding: 0.5rem; display: flex; flex-direction: column; gap: 0.2rem; }
.ch-sess {
    display: flex; align-items: center; gap: 0.55rem; padding: 0.55rem 0.6rem;
    border-radius: 8px; cursor: pointer; border: 1px solid transparent;
    transition: background 0.15s var(--ease), border-color 0.15s var(--ease);
}
.ch-sess:hover { background: var(--paper-deep); }
.ch-sess.active { background: var(--olive-soft); border-color: color-mix(in srgb, var(--olive) 26%, transparent); }
.ch-sess-dot { flex-shrink: 0; width: 7px; height: 7px; border-radius: 50%; background: var(--ink-ghost); }
.ch-sess.active .ch-sess-dot { background: var(--olive); box-shadow: 0 0 0 3px var(--olive-glow); }
.ch-sess-info { flex: 1; min-width: 0; }
.ch-sess-title { font-size: 0.8rem; color: var(--ink); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ch-sess-meta { font-size: 0.68rem; color: var(--ink-faint); font-family: var(--font-mono); margin-top: 0.1rem; }
.ch-sess-del {
    flex-shrink: 0; opacity: 0; width: 22px; height: 22px; display: grid; place-items: center;
    color: var(--ink-faint); border-radius: 5px; transition: all 0.15s var(--ease);
}
.ch-sess:hover .ch-sess-del { opacity: 1; }
.ch-sess-del:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
.ch-rail-empty { padding: 1rem 0.8rem; font-size: 0.74rem; color: var(--ink-faint); text-align: center; line-height: 1.6; }

/* ---- 右对话区 ---- */
.ch-main { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--paper); }
.ch-main-head {
    padding: 0.8rem 1.4rem; display: flex; align-items: center; gap: 0.7rem;
    border-bottom: 1px solid var(--line-soft); background: var(--paper-light);
}
.ch-status { display: flex; align-items: center; gap: 0.45rem; font-family: var(--font-mono); font-size: 0.66rem; letter-spacing: 1px; color: var(--ink-faint); text-transform: uppercase; }
.ch-status .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 16%, transparent); }
.ch-status.busy .dot { background: var(--warn); box-shadow: 0 0 0 3px color-mix(in srgb, var(--warn) 18%, transparent); animation: ch-pulse 1.1s infinite; }
.ch-llm { display: flex; align-items: center; }
.ch-llm-chip {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.5px;
    color: var(--ink-soft);
    background: var(--paper-deep);
    border: 1px solid var(--line-soft);
    border-radius: 7px;
    padding: 0.14rem 0.5rem;
    cursor: pointer;
    white-space: nowrap;
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: border-color 0.15s var(--ease), color 0.15s var(--ease);
}
.ch-llm-chip:hover { border-color: var(--olive); color: var(--olive); }
.ch-llm-chip.mock { border-style: dashed; color: var(--warn); }
.ch-llm-chip.mock:hover { color: var(--warn); border-color: var(--warn); }
.ch-llm-chip.miss { border-style: dashed; color: var(--danger); }
.ch-llm-chip.miss:hover { color: var(--danger); border-color: var(--danger); }
.ch-main-title { font-family: var(--font-serif); font-size: 1rem; font-weight: 700; color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ch-clear {
    margin-left: auto; font-size: 0.74rem; color: var(--ink-faint); cursor: pointer;
    padding: 0.35rem 0.6rem; border-radius: 6px; transition: all 0.15s var(--ease); display: flex; align-items: center; gap: 0.3rem;
}
.ch-clear:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 8%, transparent); }

/* ---- 消息流 ---- */
.ch-thread { flex: 1; overflow-y: auto; padding: 1.4rem 1.6rem 1.6rem; scroll-behavior: smooth; }
.ch-thread-inner { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 1.1rem; }

/* 空态 */
.ch-welcome { text-align: left; max-width: 560px; margin: 4vh auto 0; animation: ch-rise 0.5s var(--ease-out); }
.ch-wb-mark { width: 52px; height: 52px; border-radius: 14px; display: grid; place-items: center; font-size: 1.5rem; background: var(--olive); color: var(--paper-light); box-shadow: 2px 2px 0 var(--olive-dark); margin-bottom: 1.1rem; }
.ch-wel-title { font-family: var(--font-serif); font-size: 1.9rem; font-weight: 900; color: var(--ink); line-height: 1.2; letter-spacing: 0.5px; }
.ch-wel-title em { font-style: normal; color: var(--olive-dark); }
.ch-wel-sub { font-size: 0.9rem; color: var(--ink-soft); margin-top: 0.6rem; line-height: 1.7; }
.ch-suggests { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; margin-top: 1.6rem; }
.ch-sugg {
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 0.75rem 0.85rem; cursor: pointer; text-align: left; display: flex; gap: 0.55rem; align-items: flex-start;
    transition: all 0.18s var(--ease);
}
.ch-sugg:hover { border-color: color-mix(in srgb, var(--olive) 45%, var(--line)); box-shadow: var(--shadow-sm); transform: translateY(-2px); }
.ch-sugg-ico { font-size: 1.05rem; flex-shrink: 0; margin-top: 0.1rem; }
.ch-sugg-txt { font-size: 0.8rem; color: var(--ink-soft); line-height: 1.5; }
.ch-caps { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 1.1rem; }
.ch-cap { font-size: 0.72rem; color: var(--olive-dark); background: var(--olive-soft); border: 1px solid color-mix(in srgb, var(--olive) 18%, transparent); padding: 0.28rem 0.6rem; border-radius: 20px; font-family: var(--font-mono); letter-spacing: 0.3px; }

/* 消息行 */
.ch-msg { display: flex; gap: 0.75rem; align-items: flex-start; animation: ch-rise 0.35s var(--ease-out); max-width: 100%; }
.ch-msg.user { flex-direction: row-reverse; }
.ch-avatar { flex-shrink: 0; width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; font-size: 0.95rem; }
.ch-msg.assistant .ch-avatar { background: var(--olive); color: var(--paper-light); box-shadow: 1px 1px 0 var(--olive-dark); }
.ch-msg.user .ch-avatar { background: var(--ink); color: var(--paper-light); box-shadow: 1px 1px 0 var(--ink-soft); }
.ch-bubble { flex: 1; min-width: 0; max-width: 78%; }
.ch-msg.user .ch-bubble { display: flex; justify-content: flex-end; }
.ch-msg.user .ch-msg-pill {
    background: var(--ink); color: var(--paper-light); border-radius: 14px 14px 3px 14px;
    padding: 0.6rem 0.9rem; font-size: 0.88rem; line-height: 1.65; max-width: 100%;
    border: none;
}
.ch-msg.assistant .ch-bubble {
    background: var(--card); border: 1px solid var(--line); border-left: 3px solid var(--olive);
    border-radius: 3px 12px 12px 12px; padding: 0.9rem 1.05rem;
    box-shadow: var(--shadow-sm);
}
.ch-msg-kicker { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
.ch-msg-role { font-family: var(--font-mono); font-size: 0.62rem; letter-spacing: 1.5px; text-transform: uppercase; color: var(--ink-faint); }
.ch-msg-role b { color: var(--olive-dark); font-weight: 700; }
.ch-msg .md-h1, .ch-msg .md-h2, .ch-msg .md-h3, .ch-msg .md-h4 { font-family: var(--font-serif); color: var(--ink); line-height: 1.35; }
.ch-msg .md-h1 { font-size: 1.25rem; font-weight: 800; margin: 0.4rem 0 0.5rem; }
.ch-msg .md-h2 { font-size: 1.1rem; font-weight: 800; margin: 0.8rem 0 0.4rem; }
.ch-msg .md-h3 { font-size: 0.98rem; font-weight: 700; margin: 0.6rem 0 0.3rem; }
.ch-msg .md-p { font-size: 0.88rem; color: var(--ink-soft); line-height: 1.8; margin: 0.35rem 0; }
.ch-msg .md-ul, .ch-msg .md-ol { margin: 0.4rem 0; padding-left: 1.2rem; }
.ch-msg .md-ul li, .ch-msg .md-ol li { font-size: 0.86rem; color: var(--ink-soft); line-height: 1.8; }
.ch-msg .md-code-inline { background: var(--paper-deep); border: 1px solid var(--line-soft); border-radius: 4px; padding: 0.05rem 0.35rem; font-family: var(--font-mono); font-size: 0.8em; color: var(--olive-dark); }
.ch-msg .md-code-block { background: var(--paper-deep); border: 1px solid var(--line); border-radius: 8px; margin: 0.6rem 0; overflow: hidden; position: relative; }
.ch-msg .md-code-block .md-code-head { display: flex; align-items: center; justify-content: space-between; padding: 0.3rem 0.5rem 0.15rem 0.7rem; }
.ch-msg .md-code-block .md-code-lang { display: inline-block; font-family: var(--font-mono); font-size: 0.62rem; color: var(--ink-faint); }
.ch-msg .md-code-block pre { margin: 0; padding: 0.1rem 0.7rem 0.7rem; overflow-x: auto; }
.ch-msg .md-code-block code { font-family: var(--font-mono); font-size: 0.78rem; color: var(--ink); line-height: 1.6; }
.ch-msg .md-table-wrap { overflow-x: auto; margin: 0.6rem 0; }
.ch-msg .md-table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
.ch-msg .md-table th { background: var(--olive-soft); color: var(--olive-dark); font-family: var(--font-mono); font-size: 0.7rem; padding: 0.45rem 0.6rem; text-align: left; border: 1px solid var(--line); }
.ch-msg .md-table td { padding: 0.4rem 0.6rem; border: 1px solid var(--line); color: var(--ink-soft); }
.ch-msg .md-hr { border: none; border-top: 1px dashed var(--line); margin: 0.7rem 0; }
.ch-msg strong { color: var(--ink); font-weight: 700; }

/* 流式光标 */
.ch-cursor { display: inline-block; width: 8px; height: 1.1em; background: var(--olive); border-radius: 2px; vertical-align: -0.15em; margin-left: 2px; animation: ch-blink 0.85s infinite; }

/* 打字指示 */
.ch-typing { display: flex; align-items: center; gap: 0.4rem; color: var(--ink-faint); font-size: 0.78rem; }
.ch-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--olive); display: inline-block; animation: ch-bounce 1.2s infinite; }
.ch-typing span:nth-child(2) { animation-delay: 0.15s; }
.ch-typing span:nth-child(3) { animation-delay: 0.3s; }

/* ---- 工具活动卡 ---- */
.ch-tool {
    display: flex; align-items: center; gap: 0.65rem; margin-top: 0.6rem;
    font-family: var(--font-mono); font-size: 0.76rem; color: var(--ink-soft);
    background: var(--paper-deep); border: 1px solid var(--line-soft); border-radius: 8px;
    padding: 0.5rem 0.7rem; animation: ch-rise 0.3s var(--ease-out);
}
.ch-tool-ico { font-size: 0.95rem; }
.ch-tool-name { font-weight: 600; color: var(--ink); }
.ch-tool-state { display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; margin-left: auto; flex-shrink: 0; }
.ch-tool-state.pending { border: 2px solid var(--line); border-top-color: var(--olive); animation: ch-spin 0.8s linear infinite; }
.ch-tool-state.ok { background: color-mix(in srgb, var(--success) 14%, var(--card)); color: var(--success); font-size: 0.72rem; }
.ch-tool-state.err { background: color-mix(in srgb, var(--danger) 14%, var(--card)); color: var(--danger); font-size: 0.72rem; }
.ch-tool.err .ch-tool-name { color: var(--danger); }
.ch-tool-args { margin-left: 0.2rem; color: var(--ink-faint); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; max-width: 40%; }

/* ---- 工具过程折叠面板 ---- */
.ch-process { margin-top: 0.6rem; border: 1px solid var(--line-soft); border-radius: 8px; background: var(--paper-light); overflow: hidden; animation: ch-rise 0.3s var(--ease-out); }
.ch-process-head { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.7rem; cursor: pointer; user-select: none; transition: background 0.15s var(--ease); }
.ch-process-head:hover { background: var(--paper-deep); }
.ch-process-caret { font-size: 0.6rem; color: var(--ink-faint); transition: transform 0.2s var(--ease); }
.ch-process.collapsed .ch-process-caret { transform: rotate(-90deg); }
.ch-process-ico { font-size: 0.85rem; }
.ch-process-label { font-size: 0.74rem; color: var(--ink-soft); font-family: var(--font-mono); }
.ch-process-count { font-size: 0.68rem; color: var(--olive-dark); background: var(--olive-soft); padding: 0.05rem 0.4rem; border-radius: 8px; font-family: var(--font-mono); letter-spacing: 0.5px; }
.ch-process-status { margin-left: auto; font-size: 0.68rem; color: var(--ink-faint); font-family: var(--font-mono); }
.ch-process-status.running { color: var(--warn); display: flex; align-items: center; gap: 0.3rem; }
.ch-process-status.running::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--warn); animation: ch-pulse 1s infinite; }
.ch-process-status.done { color: var(--success); }
.ch-process-body { padding: 0 0.5rem 0.5rem; display: flex; flex-direction: column; gap: 0.4rem; }
.ch-process .ch-tool { margin-top: 0; }
.ch-process.collapsed .ch-process-body { display: none; }
.ch-process .ch-tool-state.pending { animation: ch-spin 0.8s linear infinite; }

/* ---- 会话分组 ---- */
.ch-sess-group { font-size: 0.62rem; font-family: var(--font-mono); letter-spacing: 1px; color: var(--ink-ghost); text-transform: uppercase; padding: 0.6rem 0.5rem 0.2rem; }
.ch-sess-group:first-child { padding-top: 0.2rem; }
/* ---- 会话重命名 ---- */
.ch-sess-title { font-size: 0.8rem; color: var(--ink); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.ch-rename-input { width: 100%; font-size: 0.8rem; color: var(--ink); background: var(--card); border: 1px solid var(--olive); border-radius: 5px; padding: 0.25rem 0.4rem; outline: none; box-sizing: border-box; }
.ch-sess-ops { display: flex; align-items: center; gap: 0.2rem; margin-left: auto; }
.ch-op {
    flex-shrink: 0; width: 22px; height: 22px; display: grid; place-items: center;
    color: var(--ink-faint); border-radius: 5px; opacity: 0; transition: all 0.15s var(--ease);
}
.ch-sess:hover .ch-op { opacity: 1; }
.ch-op:hover { color: var(--olive); background: var(--olive-soft); }
.ch-op.danger:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }

/* ---- 骨架屏 ---- */
.ch-skel { padding: 0.5rem 0.6rem; }
.ch-skel-line { height: 12px; border-radius: 6px; background: linear-gradient(90deg, var(--line-soft) 25%, var(--paper-deep) 40%, var(--line-soft) 60%); background-size: 200% 100%; animation: ch-shimmer 1.4s infinite; }
.ch-skel-line.short { width: 55%; }
.ch-skel-line.md { width: 80%; margin-top: 0.5rem; }
@keyframes ch-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* ---- 确认卡 ---- */
.ch-confirm {
    margin-top: 0.6rem; border: 1px solid color-mix(in srgb, var(--warn) 40%, var(--line));
    border-left: 3px solid var(--warn); border-radius: 10px; background: color-mix(in srgb, var(--warn) 6%, var(--card));
    padding: 0.75rem 0.9rem; animation: ch-rise 0.35s var(--ease-out);
}
.ch-confirm-title { display: flex; align-items: center; gap: 0.5rem; font-weight: 700; color: var(--ink); font-size: 0.86rem; }
.ch-confirm-title .cf-ico { color: var(--warn); }
.ch-confirm-desc { font-size: 0.8rem; color: var(--ink-soft); margin-top: 0.35rem; line-height: 1.6; }
.ch-confirm-args { margin-top: 0.4rem; font-family: var(--font-mono); font-size: 0.72rem; color: var(--ink-faint); background: var(--card); border: 1px solid var(--line-soft); border-radius: 6px; padding: 0.4rem 0.55rem; word-break: break-all; max-height: 140px; overflow: auto; }
.ch-confirm-actions { display: flex; gap: 0.5rem; margin-top: 0.7rem; }
.ch-btn { font-size: 0.78rem; font-weight: 600; padding: 0.45rem 0.9rem; border-radius: 7px; border: 1px solid transparent; cursor: pointer; transition: all 0.15s var(--ease); }
.ch-btn-app { background: var(--warn); color: var(--paper-light); }
.ch-btn-app:hover { background: color-mix(in srgb, var(--warn) 85%, var(--ink)); }
.ch-btn-app:disabled { opacity: 0.5; cursor: not-allowed; }
.ch-btn-cancel { background: var(--card); color: var(--ink-soft); border-color: var(--line); }
.ch-btn-cancel:hover { color: var(--ink); }

/* ---- 导航提示卡 ---- */
.ch-nav-card { margin-top: 0.6rem; display: flex; align-items: center; gap: 0.6rem; background: var(--olive-soft); border: 1px solid color-mix(in srgb, var(--olive) 26%, transparent); border-radius: 8px; padding: 0.5rem 0.75rem; cursor: pointer; animation: ch-rise 0.3s var(--ease-out); transition: all 0.15s var(--ease); }
.ch-nav-card:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.ch-nav-ico { font-size: 1rem; }
.ch-nav-txt { font-size: 0.8rem; color: var(--olive-dark); font-weight: 600; }

/* ---- 错误卡 ---- */
.ch-error { margin-top: 0.5rem; font-size: 0.8rem; color: var(--danger); background: color-mix(in srgb, var(--danger) 7%, var(--card)); border: 1px solid color-mix(in srgb, var(--danger) 25%, var(--line)); border-radius: 8px; padding: 0.6rem 0.8rem; }

/* ---- 输入区 ---- */
.ch-composer { border-top: 1px solid var(--line-soft); background: var(--paper-light); padding: 0.8rem 1.4rem 1.1rem; }
.ch-composer-inner { max-width: 860px; margin: 0 auto; }
.ch-input-shell { display: flex; align-items: flex-end; gap: 0.6rem; background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 0.55rem 0.6rem 0.55rem 0.95rem; transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease); }
.ch-input-shell:focus-within { border-color: var(--olive); box-shadow: 0 0 0 3px var(--olive-glow); }
.ch-input { flex: 1; border: none; outline: none; background: transparent; color: var(--ink); font-family: var(--font-sans); font-size: 0.9rem; line-height: 1.5; resize: none; max-height: 140px; }
.ch-input::placeholder { color: var(--ink-ghost); }
.ch-send {
    flex-shrink: 0; width: 36px; height: 36px; border-radius: 9px; border: none; cursor: pointer;
    background: var(--olive); color: var(--paper-light); display: grid; place-items: center;
    transition: all 0.18s var(--ease); position: relative;
}
.ch-send:hover { background: var(--olive-dark); transform: translateY(-1px); }
.ch-send:disabled { opacity: 0.45; cursor: not-allowed; transform: none; }
.ch-send.stop { background: var(--warn); }
.ch-hint { text-align: center; font-size: 0.68rem; color: var(--ink-ghost); margin-top: 0.4rem; font-family: var(--font-mono); letter-spacing: 0.5px; }

/* ---- 回到底部浮动按钮 ---- */
.ch-scroll-down {
    position: absolute; right: 1.4rem; bottom: 5.5rem; z-index: 12;
    display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%;
    background: var(--card); border: 1px solid var(--line); color: var(--ink-soft);
    box-shadow: var(--shadow-md); cursor: pointer; opacity: 0; pointer-events: none;
    transform: translateY(8px); transition: all 0.2s var(--ease);
}
.ch-scroll-down.show { opacity: 1; pointer-events: auto; transform: translateY(0); }
.ch-scroll-down:hover { color: var(--olive); border-color: var(--olive); }
/* ---- 消息操作条（assistant hover） ---- */
.ch-msg-actions {
    display: flex; align-items: center; gap: 0.15rem; margin-top: 0.5rem;
    opacity: 0; transform: translateY(-3px); transition: all 0.18s var(--ease);
}
.ch-msg.assistant.streaming .ch-msg-actions { opacity: 0; pointer-events: none; }
.ch-msg.assistant:hover .ch-msg-actions { opacity: 1; transform: translateY(0); }
.ch-act-btn {
    display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.28rem 0.55rem;
    font-size: 0.7rem; color: var(--ink-faint); background: transparent; border: none;
    border-radius: 6px; cursor: pointer; font-family: var(--font-sans);
    transition: all 0.14s var(--ease);
}
.ch-act-btn:hover { color: var(--olive); background: var(--paper-deep); }
.ch-act-btn.copied { color: var(--success); }
.ch-act-small { padding: 0.28rem 0.4rem; }
/* ---- 用户消息 hover 编辑 ---- */
.ch-user-edit {
    position: absolute; top: 50%; right: -1.6rem; transform: translateY(-50%);
    width: 24px; height: 24px; display: grid; place-items: center; border-radius: 6px;
    color: var(--ink-faint); opacity: 0; cursor: pointer; transition: all 0.15s var(--ease);
}
.ch-msg.user:hover .ch-user-edit { opacity: 1; }
.ch-user-edit:hover { color: var(--olive); background: var(--paper-deep); }
.ch-user-edit-area { position: relative; max-width: 100%; }
.ch-msg.user .ch-msg-pill.editing {
    background: var(--paper-light); color: var(--ink); border: 1px solid var(--olive);
    border-radius: 12px; padding: 0; overflow: hidden;
}
.ch-user-edit-area textarea { width: 100%; border: none; outline: none; background: transparent; color: var(--ink); font-size: 0.88rem; line-height: 1.65; padding: 0.6rem 0.9rem; resize: none; font-family: var(--font-sans); }
.ch-user-edit-ops { display: flex; gap: 0.4rem; padding: 0 0.5rem 0.5rem; justify-content: flex-end; }
/* ---- 代码块复制按钮 ---- */
.ch-msg .md-code-block { position: relative; }
.ch-msg .md-copy-btn {
    position: absolute; top: 0.35rem; right: 0.4rem; z-index: 2;
    display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.18rem 0.45rem;
    font-size: 0.66rem; color: var(--ink-faint); background: var(--card);
    border: 1px solid var(--line-soft); border-radius: 6px; cursor: pointer;
    font-family: var(--font-mono); opacity: 0; transition: all 0.14s var(--ease);
}
.ch-msg .md-code-block:hover .md-copy-btn { opacity: 1; }
.ch-msg .md-copy-btn.copied { color: var(--success); border-color: color-mix(in srgb, var(--success) 40%, var(--line)); }
/* ---- 追问 chips ---- */
.ch-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.6rem; animation: ch-rise 0.3s var(--ease-out); }
.ch-chip {
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.32rem 0.7rem;
    font-size: 0.76rem; color: var(--olive-dark); background: var(--olive-soft);
    border: 1px solid color-mix(in srgb, var(--olive) 20%, transparent); border-radius: 20px;
    cursor: pointer; transition: all 0.15s var(--ease);
}
.ch-chip:hover { background: color-mix(in srgb, var(--olive) 16%, var(--paper-light)); transform: translateY(-1px); }
.ch-chip .ch-chip-ico { font-size: 0.82rem; }
/* ---- 会话栏折叠 ---- */
.ch-app.rail-closed { grid-template-columns: 0 1fr; }
.ch-app .ch-rail { transition: opacity 0.18s var(--ease), transform 0.18s var(--ease); }
.ch-app.rail-closed .ch-rail { opacity: 0; pointer-events: none; }
/* 会话栏折叠/展开按钮（桌面端顶栏） */
.ch-rail-collapse {
    display: grid; place-items: center; width: 30px; height: 30px; margin-left: auto;
    border-radius: 7px; border: 1px solid var(--line); color: var(--ink-soft);
    background: var(--card); cursor: pointer; transition: all 0.15s var(--ease);
}
.ch-rail-collapse:hover { color: var(--olive); border-color: color-mix(in srgb, var(--olive) 40%, var(--line)); }

/* ---- 动画 ---- */
@keyframes ch-rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes ch-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@keyframes ch-bounce { 0%, 100% { transform: translateY(0); opacity: 0.3; } 50% { transform: translateY(-4px); opacity: 1; } }
@keyframes ch-spin { to { transform: rotate(360deg); } }
@keyframes ch-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

/* ---- 响应式 ---- */
@media (max-width: 860px) {
    .ch-app { grid-template-columns: 1fr; }
    .ch-rail { position: absolute; left: 0; top: 0; bottom: 0; width: 260px; z-index: 20; transform: translateX(-100%); transition: transform 0.25s var(--ease); box-shadow: var(--shadow-lg); }
    .ch-rail.open { transform: translateX(0); }
    .ch-rail-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.25); z-index: 15; display: none; }
.ch-rail-backdrop.open { display: block; }
.ch-rail-toggle {
    display: none; align-items: center; justify-content: center;
    width: 30px; height: 30px; margin-left: auto; border-radius: 7px;
    background: var(--olive-soft); color: var(--olive-dark); border: 1px solid color-mix(in srgb, var(--olive) 25%, transparent);
    font-size: 0.9rem; cursor: pointer;
}
.ch-rail-collapse { display: none; }
.ch-suggests { grid-template-columns: 1fr; }
.ch-msg .ch-bubble { max-width: 88%; }
}`;
        document.head.appendChild(style);
    }

    // ============ 工具函数 ============

    function toolMeta(name) {
        return { icon: TOOL_ICONS[name] || '⚙️', label: TOOL_NAMES[name] || name };
    }

    function briefArgs(args) {
        if (!args) return '';
        try {
            const s = JSON.stringify(args);
            return s.length > 42 ? s.slice(0, 42) + '…' : s;
        } catch (e) { return ''; }
    }

    function scrollToBottom(force) {
        const th = root && root.querySelector('.ch-thread');
        if (!th) return;
        requestAnimationFrame(() => {
            // 非强制滚动时，若用户已上翻浏览，则不抢占滚动位置
            if (!force && !state.pinnedBottom) {
                updateScrollDownButton();
                return;
            }
            th.scrollTop = th.scrollHeight;
            state.pinnedBottom = true;
            updateScrollDownButton();
        });
    }

    function onThreadScroll() {
        const th = root && root.querySelector('.ch-thread');
        if (!th) return;
        const dist = th.scrollHeight - th.clientHeight - th.scrollTop;
        state.pinnedBottom = dist < 72;
        updateScrollDownButton();
    }

    function updateScrollDownButton() {
        const btn = root && root.querySelector('#ch-scroll-down');
        if (!btn) return;
        const show = !state.pinnedBottom && !state.thinking;
        btn.classList.toggle('show', show);
    }

    function setBusy(busy) {
        const st = root && root.querySelector('#ch-main-head');
        if (st) st.classList.toggle('busy', busy);
        const send = root && root.querySelector('#ch-send');
        if (send) {
            send.disabled = !!state.thinking;
            send.classList.toggle('stop', !!state.thinking);
        }
    }

    // ============ LLM 配置状态 ============

    // 供应商显示名
    const PROVIDER_NAMES = { openai: 'OpenAI', deepseek: 'DeepSeek', qwen: '通义千问', mock: 'Mock 本地' };

    // 拉取 LLM 配置（脱敏），更新顶部状态 chip
    async function loadLlmStatus() {
        const chip = root && root.querySelector('#ch-llm-chip');
        if (!chip) return;
        try {
            const data = await API.get('/settings/llm');
            state.llmStatus = data;
            renderLlmStatus();
        } catch (e) {
            chip.textContent = 'LLM 配置获取失败';
            chip.className = 'ch-llm-chip miss';
        }
    }

    function renderLlmStatus() {
        const chip = root && root.querySelector('#ch-llm-chip');
        const cfg = state.llmStatus;
        if (!chip || !cfg) return;
        const agent = cfg.agent || {};
        const provider = agent.provider || '';
        const model = agent.model || '';
        const mock = !!cfg.mock_fallback;

        let label, cls;
        if (provider === 'mock') {
            label = '⚡ Mock 本地模式';
            cls = 'mock';
        } else if (!agent.configured) {
            label = '⚠ 未配置模型';
            cls = 'miss';
        } else {
            label = `● ${PROVIDER_NAMES[provider] || provider} · ${model}`;
            cls = '';
        }
        chip.textContent = label;
        chip.className = 'ch-llm-chip ' + (cls || '').trim();
    }

    // ============ SSE 渲染 ============

    function handleEvent(evt) {
        if (!state.thinking) return;
        if (evt.type === 'content_delta') {
            appendAssistantDelta(evt.delta || '');
        } else if (evt.type === 'tool_call_start') {
            addToolCard(evt.tool_call || {});
        } else if (evt.type === 'tool_result') {
            settleToolCard(evt.tool_call_id || evt.tool_name, evt.success !== false, evt.error || '');
        } else if (evt.type === 'confirm_required') {
            addConfirmCard(evt);
        } else if (evt.type === 'navigate') {
            addNavCard(evt);
        } else if (evt.type === 'done') {
            state.thinking = false;
            state.currentId = evt.session_id || state.currentId;
            const updated = state.sessions.find(s => s.id === state.currentId);
            if (updated) state.currentTitle = updated.title || state.currentTitle;
            finishStreaming();
            loadSessions();
            updateMainTitle();
            refocusInput();
        } else if (evt.type === 'error') {
            state.thinking = false;
            addError(evt.message || '出错了，请稍后再试');
            setBusy(false);
        }
    }

    function appendAssistantDelta(delta) {
        const thread = root.querySelector('.ch-thread-inner');
        let msg = thread.querySelector('.ch-msg.assistant.streaming');
        if (!msg) {
            msg = createAssistantBubble();
            thread.appendChild(msg);
            msg.classList.add('streaming');
            scrollToBottom();
        }
        const textEl = msg.querySelector('.ch-md-body');
        textEl.dataset.buffer = (textEl.dataset.buffer || '') + delta;
        textEl.innerHTML = MD.render(textEl.dataset.buffer) + '<span class="ch-cursor"></span>';
        // 一旦有正文输出，收掉"思考中"指示
        const think = msg.querySelector('.ch-msg-kicker .ch-process-status');
        if (think && think.classList.contains('running')) think.remove();
        scrollToBottom();
    }

    function createAssistantBubble() {
        const el = document.createElement('div');
        el.className = 'ch-msg assistant';
        el.innerHTML = `
            <div class="ch-avatar">🧭</div>
            <div class="ch-bubble">
                <div class="ch-msg-kicker"><span class="ch-msg-role">AI 求职教练 · <b>3 号</b></span>${state.thinking ? '<span class="ch-process-status running" style="margin-left:auto;font-size:0.62rem;">思考中</span>' : ''}</div>
                <div class="ch-md-body" data-buffer=""></div>
                <div class="ch-process" style="display:none;">
                    <div class="ch-process-head">
                        <span class="ch-process-caret">▾</span>
                        <span class="ch-process-ico">⚙️</span>
                        <span class="ch-process-label">调用工具</span>
                        <span class="ch-process-count">0</span>
                        <span class="ch-process-status running">执行中</span>
                    </div>
                    <div class="ch-process-body"></div>
                </div>
            </div>`;
        root.querySelector('.ch-thread-inner').appendChild(el);
        bindProcessToggle(el);
        return el;
    }

    function bindProcessToggle(msgEl) {
        const head = msgEl.querySelector('.ch-process-head');
        const proc = msgEl.querySelector('.ch-process');
        if (head) head.addEventListener('click', () => proc.classList.toggle('collapsed'));
    }

    function finalizeAssistant(assistantEl) {
        if (!assistantEl) return;
        assistantEl.classList.remove('streaming');
        const kicker = assistantEl.querySelector('.ch-msg-kicker');
        // 移除"思考中"指示
        const think = kicker && kicker.querySelector('.ch-process-status.running');
        if (think) think.remove();
        const textEl = assistantEl.querySelector('.ch-md-body');
        // 移除流式光标
        const cursor = textEl.querySelector('.ch-cursor');
        if (cursor) cursor.remove();
        // 若有工具过程，则在完成后折叠为摘要（保留"已完成"状态，可点击展开）
        const proc = assistantEl.querySelector('.ch-process');
        if (proc && proc.querySelector('.ch-tool')) {
            proc.classList.add('collapsed');
            // 兜底：若中途遗漏状态更新，确保不是 executing
            if (proc.querySelector('.ch-tool-state.pending')) {
                proc.querySelectorAll('.ch-tool-state.pending').forEach(p => {
                    p.className = 'ch-tool-state ok'; p.textContent = '✓'; p.style.animation = 'none';
                });
                setProcessStatus(proc, 'done', '已完成');
            }
        }
        // 若没有文本内容也没有工具，隐藏空气泡；否则保证显示
        const bubble = assistantEl.querySelector('.ch-bubble');
        if (!textEl.dataset.buffer && !(proc && proc.querySelector('.ch-tool'))) {
            bubble.style.display = 'block';
        } else {
            bubble.style.display = '';
        }
        // 完成后追加操作条 + 追问 chips
        appendActionBar(assistantEl);
        appendFollowups(assistantEl);
    }

    function currentAssistantEl() {
        const thread = root.querySelector('.ch-thread-inner');
        return thread.querySelector('.ch-msg.assistant.streaming') ||
               thread.querySelector('.ch-msg.assistant:last-of-type');
    }

    function addToolCard(call) {
        const name = (call && call.name) || 'unknown_tool';
        const args = (call && call.arguments) || {};
        const meta = toolMeta(name);
        const thread = root.querySelector('.ch-thread-inner');
        const card = document.createElement('div');
        card.className = 'ch-tool';
        card.dataset.toolId = (call && call.id) || 'tool_' + (msgSeq++);
        card.innerHTML = `
            <span class="ch-tool-ico">${meta.icon}</span>
            <span class="ch-tool-name">${esc(meta.label)}</span>
            <span class="ch-tool-args">${esc(briefArgs(args))}</span>
            <span class="ch-tool-state pending"></span>`;
        // 找到宿主助手，把工具卡放入其过程折叠面板
        const host = currentAssistantEl();
        const proc = host ? host.querySelector('.ch-process') : null;
        if (proc) {
            proc.style.display = '';
            proc.classList.remove('collapsed');           // 执行中保持展开
            proc.querySelector('.ch-process-body').appendChild(card);
            bumpProcessCount(proc, 1);
            setProcessStatus(proc, 'running', '执行中');
        } else {
            thread.appendChild(card);
        }
        scrollToBottom();
    }

    function bumpProcessCount(proc, delta) {
        const cntEl = proc.querySelector('.ch-process-count');
        const cur = parseInt(cntEl.textContent, 10) || 0;
        cntEl.textContent = Math.max(0, cur + delta);
    }

    function setProcessStatus(proc, cls, text) {
        const st = proc.querySelector('.ch-process-status');
        st.className = 'ch-process-status ' + cls;
        st.textContent = text;
    }

    function settleToolCard(id, ok, errText) {
        const thread = root.querySelector('.ch-thread-inner');
        const card = Array.from(thread.querySelectorAll('.ch-tool')).find(c =>
            c.dataset.toolId === id ||
            (c.querySelector('.ch-tool-name').textContent === (TOOL_NAMES[id] || id))
        );
        if (!card) return;
        const st = card.querySelector('.ch-tool-state');
        st.className = 'ch-tool-state ' + (ok ? 'ok' : 'err');
        st.textContent = ok ? '✓' : '✗';
        st.style.animation = 'none';
        if (!ok) card.classList.add('err');
        if (errText) card.title = errText;
        // 同步：该工具已结算，宿主过程面板不再需要展开态
        const proc = card.closest('.ch-process');
        if (proc) {
            const anyPending = proc.querySelector('.ch-tool-state.pending');
            if (!anyPending) setProcessStatus(proc, ok ? 'done' : 'err', ok ? '已完成' : '有失败');
        }
    }

    function addConfirmCard(evt) {
        const thread = root.querySelector('.ch-thread-inner');
        let host = currentAssistantEl();
        if (!host) host = createAssistantBubble();
        const wrap = host.querySelector('.ch-bubble');
        const card = document.createElement('div');
        card.className = 'ch-confirm';
        const argsText = JSON.stringify(evt.arguments || {}, null, 2);
        card.innerHTML = `
            <div class="ch-confirm-title"><span class="cf-ico">⚠️</span>需要你的确认</div>
            <div class="ch-confirm-desc">${esc(evt.description || '是否执行此操作？')}（${esc(TOOL_NAMES[evt.tool_name] || evt.tool_name)}）</div>
            <div class="ch-confirm-args">${esc(argsText)}</div>
            <div class="ch-confirm-actions">
                <button class="ch-btn ch-btn-app" data-approve="1">确认执行</button>
                <button class="ch-btn ch-btn-cancel" data-approve="0">取消</button>
            </div>`;
        wrap.appendChild(card);
        wrap.style.display = '';
        bindConfirm(card, evt.action_id, evt);
        scrollToBottom();
    }

    function bindConfirm(card, actionId, evt) {
        card.querySelectorAll('.ch-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                btn.disabled = true;
                const approve = btn.dataset.approve === '1';
                // 立即隐藏确认按钮，避免重复点击
                card.querySelector('.ch-confirm-actions').style.display = 'none';
                card.querySelector('.ch-confirm-desc').textContent =
                    approve ? '正在执行…' : '已取消该操作。';
                submitConfirm(actionId, approve, card);
            });
        });
    }

    async function submitConfirm(actionId, approved, card) {
        if (!state.currentId) return; // 无会话 id，确认失效
        // 恢复流期间也要消费事件：临时置为 thinking，恢复结束归位
        const wasThinking = state.thinking;
        state.thinking = true;
        setBusy(true);
        try {
            await API.stream('/agent/confirm', {
                action_id: actionId,
                approved: approved,
                session_id: state.currentId,
            }, (evt) => {
                if (evt.type === 'done') {
                    if (card) card.querySelector('.ch-confirm-desc').textContent = '已完成。';
                    if (card) card.querySelector('.ch-confirm-actions').style.display = 'none';
                }
                handleEvent(evt);
            });
        } catch (e) {
            API.toast(e.message || '确认失败', 'error');
        } finally {
            // 恢复流结束时，若 done 事件未自行复位，则恢复到调用前的 thinking 状态
            if (state.thinking && !wasThinking) { state.thinking = false; setBusy(false); }
        }
    }

    function addNavCard(evt) {
        const target = evt.target || '/kanban';
        const routeNames = {
            '/overview': '投递总览', '/kanban': '投递看板', '/profile': '简历画像',
            '/interview': '面试复盘', '/community': '社区广场', '/job-shares': '投递分享', '/settings': '设置',
        };
        const thread = root.querySelector('.ch-thread-inner');
        let host = currentAssistantEl();
        if (!host) host = createAssistantBubble();
        const wrap = host.querySelector('.ch-bubble');
        const card = document.createElement('div');
        card.className = 'ch-nav-card';
        card.innerHTML = `<span class="ch-nav-ico">🧭</span><span class="ch-nav-txt">${esc(evt.message || '去' + (routeNames[target] || target))} →</span>`;
        card.addEventListener('click', () => Router.navigate(target, evt.params || {}));
        wrap.appendChild(card);
        wrap.style.display = '';
        scrollToBottom();
    }

    function addError(message) {
        const thread = root.querySelector('.ch-thread-inner');
        let host = currentAssistantEl();
        if (!host) host = createAssistantBubble();
        const wrap = host.querySelector('.ch-bubble');
        const errEl = document.createElement('div');
        errEl.className = 'ch-error';
        errEl.textContent = message;
        wrap.appendChild(errEl);
        wrap.style.display = '';
        scrollToBottom();
    }

    function finishStreaming() {
        const thread = root.querySelector('.ch-thread-inner');
        const streaming = thread.querySelector('.ch-msg.assistant.streaming');
        if (streaming) finalizeAssistant(streaming);
        setBusy(false);
    }

    // ============ 发送 ============

    // 通用生成入口：addUserBubble=true 时先追加用户气泡（正常发送），false 用于"重新生成/编辑重发"
    async function runGeneration(text, addUserBubble) {
        const trimmed = (text || '').trim();
        if (!trimmed || state.thinking) return;

        if (addUserBubble !== false) appendUser(trimmed, true);

        // 每轮新建 assistant 气泡容器（工具卡会挂进来）
        const assistantEl = createAssistantBubble();
        assistantEl.classList.add('streaming');

        state.thinking = true;
        setBusy(true);

        const ctrl = new AbortController();
        state.abort = ctrl;

        try {
            await API.stream('/agent/chat', {
                message: trimmed,
                session_id: state.currentId || null,
            }, (evt) => handleEvent(evt));
        } catch (e) {
            if (e.name === 'AbortError') {
                addError('已停止生成。');
            } else {
                addError(e.message || '网络异常，请检查连接。');
            }
            state.thinking = false;
            setBusy(false);
        } finally {
            state.abort = null;
        }
    }

    async function sendMessage(text) {
        return runGeneration(text, true);
    }

    function refocusInput() {
        const input = root && root.querySelector('#ch-input');
        if (input && document.activeElement !== input) {
            // 请求下一帧聚焦，避免打断刚点的建议卡片
            requestAnimationFrame(() => { try { input.focus(); } catch (e) {} });
        }
    }

    function appendUser(text, editable) {
        const thread = root.querySelector('.ch-thread-inner');
        const row = document.createElement('div');
        row.className = 'ch-msg user';
        row.innerHTML = `
            <div class="ch-avatar">👤</div>
            <div class="ch-bubble"><div class="ch-user-edit-area">
                <div class="ch-msg-pill">${esc(text)}</div>
                ${editable ? '<button class="ch-user-edit" title="编辑并重新发送" aria-label="编辑"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg></button>' : ''}
            </div></div>`;
        thread.appendChild(row);
        if (editable) {
            row.querySelector('.ch-user-edit').addEventListener('click', (e) => e.stopPropagation() || beginEditUser(row, text));
        }
        scrollToBottom();
    }

    function beginEditUser(row, originalText) {
        if (state.thinking) { API.toast('正在回答中，请稍候', 'info'); return; }
        const area = row.querySelector('.ch-user-edit-area');
        const pill = row.querySelector('.ch-msg-pill');
        pill.classList.add('editing');
        const ta = document.createElement('textarea');
        ta.value = originalText;
        ta.rows = 1;
        const renderOps = document.createElement('div');
        renderOps.className = 'ch-user-edit-ops';
        const sendBtn = document.createElement('button'); sendBtn.className = 'ch-act-btn'; sendBtn.textContent = '发送';
        sendBtn.style.color = 'var(--olive)';
        const cancelBtn = document.createElement('button'); cancelBtn.className = 'ch-act-btn'; cancelBtn.textContent = '取消';
        const autoGrow = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 140) + 'px'; };
        ta.addEventListener('input', autoGrow);
        sendBtn.addEventListener('click', () => {
            const v = ta.value.trim(); if (!v) return;
            // 编辑重发：替换本条及后续 session 上下文 —— 移除本条之后所有消息，重新生成
            let cur = row.nextElementSibling;
            while (cur) { const n = cur.nextElementSibling; cur.remove(); cur = n; }
            pill.textContent = v; pill.classList.remove('editing');
            area.removeChild(ta); area.removeChild(renderOps);
            runGeneration(v, false);
        });
        cancelBtn.addEventListener('click', () => {
            pill.classList.remove('editing');
            area.removeChild(ta); area.removeChild(renderOps);
        });
        renderOps.appendChild(sendBtn); renderOps.appendChild(cancelBtn);
        area.appendChild(ta); area.appendChild(renderOps);
        ta.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendBtn.click(); }
            else if (e.key === 'Escape') { e.preventDefault(); cancelBtn.click(); }
        });
        setTimeout(() => { try { ta.focus(); ta.select(); } catch (e) {} }, 0);
    }

    // ============ 会话管理 ============

    async function loadSessions() {
        showSessionsSkeleton();
        try {
            state.sessions = await API.get('/agent/sessions?limit=50');
        } catch (e) {
            state.sessions = [];
        }
        renderSessions();
    }

    function showSessionsSkeleton() {
        const listEl = root.querySelector('#ch-rail-list');
        if (!listEl) return;
        listEl.innerHTML = `
            <div class="ch-skel"><div class="ch-skel-line short"></div></div>
            <div class="ch-skel"><div class="ch-skel-line"></div><div class="ch-skel-line md"></div></div>
            <div class="ch-skel"><div class="ch-skel-line"></div><div class="ch-skel-line md"></div></div>`;
    }

    function renderSessions() {
        const listEl = root.querySelector('#ch-rail-list');
        if (!listEl) return;
        if (!state.sessions.length) {
            listEl.innerHTML = '<div class="ch-rail-empty">还没有对话记录<br>点击上方「新的对话」开始 🌱</div>';
            return;
        }
        // 按时间分桶：今天 / 更早
        const buckets = { today: [], earlier: [] };
        const startToday = new Date(); startToday.setHours(0, 0, 0, 0);
        state.sessions.forEach(s => {
            const d = new Date(s.updated_at);
            buckets[(!isNaN(d) && d >= startToday) ? 'today' : 'earlier'].push(s);
        });
        const groups = [
            { key: 'today', label: '今天', items: buckets.today },
            { key: 'earlier', label: '更早', items: buckets.earlier },
        ].filter(g => g.items.length);

        let html = '';
        groups.forEach(g => {
            html += `<div class="ch-sess-group">${g.label}</div>`;
            html += g.items.map(s => {
                const active = s.id === state.currentId;
                const time = fmtSessionTime(s.updated_at);
                return `
                <div class="ch-sess ${active ? 'active' : ''}" data-id="${esc(s.id)}">
                    <span class="ch-sess-dot"></span>
                    <div class="ch-sess-info">
                        <div class="ch-sess-title" title="点击重命名">${esc(s.title || '未命名会话')}</div>
                        <div class="ch-sess-meta">${s.message_count} 条 · ${esc(time)}</div>
                    </div>
                    <div class="ch-sess-ops">
                        <button class="ch-op" data-rename="${esc(s.id)}" title="重命名">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
                        </button>
                        <button class="ch-op danger" data-del="${esc(s.id)}" title="删除会话">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                </div>`;
            }).join('');
        });
        listEl.innerHTML = html;
        bindSessionEvents();
    }

    function fmtSessionTime(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (isNaN(d)) return '';
        const now = new Date();
        const diff = now - d;
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前';
        const pad = n => String(n).padStart(2, '0');
        return d.getMonth() + 1 + '-' + d.getDate() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }

    function bindSessionEvents() {
        const listEl = root.querySelector('#ch-rail-list');
        listEl.querySelectorAll('.ch-sess').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.closest('.ch-sess-ops')) return;
                const id = row.dataset.id;
                if (id === state.currentId) return;
                if (state.thinking) { API.toast('正在回答中，请稍候', 'info'); return; }
                openSession(id, row);
            });
            // 双击标题重命名
            const titleEl = row.querySelector('.ch-sess-title');
            if (titleEl) titleEl.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                startRename(row.dataset.id);
            });
        });
        listEl.querySelectorAll('[data-rename]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                startRename(btn.dataset.rename);
            });
        });
        listEl.querySelectorAll('[data-del]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = btn.dataset.del;
                if (confirm('确定删除这个会话吗？')) deleteSession(id);
            });
        });
    }

    function startRename(id) {
        const row = root.querySelector('.ch-sess[data-id="' + id + '"]');
        if (!row) return;
        const info = row.querySelector('.ch-sess-info');
        const curTitle = state.sessions.find(s => s.id === id)?.title || '';
        info.innerHTML = `<input class="ch-rename-input" value="${esc(curTitle)}" maxlength="100" autofocus />`;
        const input = info.querySelector('.ch-rename-input');
        // 提交 / 取消
        const commit = async () => {
            const v = input.value.trim();
            if (v) {
                try { await API.patch('/agent/sessions/' + encodeURIComponent(id), { title: v }); }
                catch (err) { API.toast(err.message || '重命名失败', 'error'); }
            }
            loadSessions();
            if (id === state.currentId) { state.currentTitle = v || state.currentTitle; updateMainTitle(); }
        };
        const cancel = () => loadSessions();
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); commit(); }
            else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
        });
        input.addEventListener('blur', commit);
        // 阻止点击冒泡（避免误触打开会话）
        info.addEventListener('click', (e) => e.stopPropagation());
        setTimeout(() => { try { input.select(); input.focus(); } catch (e) {} }, 0);
    }

    async function openSession(id, row) {
        row.classList.add('loading');
        try {
            const data = await API.get('/agent/sessions/' + encodeURIComponent(id));
            state.currentId = data.id;
            state.currentTitle = data.title || '未命名会话';
            renderThreadFromHistory(data.messages || []);
            updateMainTitle();
            loadSessions();
        } catch (e) {
            API.toast(e.message || '加载失败', 'error');
        } finally {
            row.classList.remove('loading');
        }
    }

    function updateMainTitle() {
        const el = root.querySelector('#ch-main-title');
        if (el) el.textContent = state.currentTitle || '新的对话';
    }

    function renderThreadFromHistory(messages) {
        const thread = root.querySelector('.ch-thread-inner');
        thread.innerHTML = '';
        let lastToolHost = null;

        messages.forEach(m => {
            const role = m.role || 'assistant';
            if (role === 'user') {
                appendUser(m.content || '', false);   // 历史会话不再提供编辑重发，避免上下文不一致
                lastToolHost = null;
            } else if (role === 'assistant') {
                const el = createAssistantBubbleNode();
                const content = typeof m.content === 'string' ? m.content : '';
                const textEl = el.querySelector('.ch-md-body');
                textEl.dataset.buffer = content;
                textEl.innerHTML = MD.render(content);
                const proc = el.querySelector('.ch-process');
                // 渲染已落库的工具调用（放进可折叠过程面板）
                if ((m.tool_calls && m.tool_calls.length)) {
                    proc.style.display = '';
                    m.tool_calls.forEach(tc => {
                        const meta = toolMeta(tc.name);
                        const card = document.createElement('div');
                        card.className = 'ch-tool';
                        card.dataset.toolId = tc.id || '';
                        card.innerHTML = `
                            <span class="ch-tool-ico">${meta.icon}</span>
                            <span class="ch-tool-name">${esc(meta.label)}</span>
                            <span class="ch-tool-args">${esc(briefArgs(tc.arguments))}</span>
                            <span class="ch-tool-state ok">✓</span>`;
                        proc.querySelector('.ch-process-body').appendChild(card);
                        bumpProcessCount(proc, 1);
                    });
                    proc.classList.add('collapsed');
                    setProcessStatus(proc, 'done', '已完成');
                }
                if (!content && !(proc && proc.querySelector('.ch-tool'))) {
                    el.querySelector('.ch-bubble').style.display = 'none';
                }
                lastToolHost = el;
            } else if (role === 'tool') {
                // tool 结果：更新最后一个工具卡为完成态
                if (lastToolHost) {
                    const cards = lastToolHost.querySelectorAll('.ch-tool');
                    const card = cards[cards.length - 1];
                    if (card) {
                        const st = card.querySelector('.ch-tool-state');
                        st.className = 'ch-tool-state ok'; st.textContent = '✓';
                    }
                }
            }
        });

        scrollToBottom();
    }

    function createAssistantBubbleNode() {
        const el = document.createElement('div');
        el.className = 'ch-msg assistant';
        el.innerHTML = `
            <div class="ch-avatar">🧭</div>
            <div class="ch-bubble">
                <div class="ch-msg-kicker"><span class="ch-msg-role">AI 求职教练 · <b>3 号</b></span></div>
                <div class="ch-md-body" data-buffer=""></div>
                <div class="ch-process" style="display:none;">
                    <div class="ch-process-head">
                        <span class="ch-process-caret">▾</span>
                        <span class="ch-process-ico">⚙️</span>
                        <span class="ch-process-label">调用工具</span>
                        <span class="ch-process-count">0</span>
                        <span class="ch-process-status done">已完成</span>
                    </div>
                    <div class="ch-process-body"></div>
                </div>
            </div>`;
        root.querySelector('.ch-thread-inner').appendChild(el);
        bindProcessToggle(el);
        return el;
    }

    async function deleteSession(id) {
        try {
            await API.del('/agent/sessions/' + encodeURIComponent(id));
            if (id === state.currentId) newChat();
            loadSessions();
            API.toast('会话已删除', 'success');
        } catch (e) {
            API.toast(e.message || '删除失败', 'error');
        }
    }

    function newChat() {
        if (state.thinking) return;
        state.currentId = null;
        state.currentTitle = '';
        renderWelcome();
        updateMainTitle();
        renderSessions();
        root.querySelector('.ch-rail') && root.querySelector('.ch-rail').classList.remove('open');
        root.querySelector('.ch-rail-backdrop') && root.querySelector('.ch-rail-backdrop').classList.remove('open');
        refocusInput();
    }

    // ============ 渲染 ============

    function renderWelcome() {
        const thread = root.querySelector('.ch-thread-inner');
        const caps = ['岗位把关 🛡️', '匹配评分 📏', '简历改写 📝', '面试演练 🎤', '投递复盘 📊', '公司调研 🏛️'];
        thread.innerHTML = `
            <div class="ch-welcome">
                <div class="ch-wb-mark">🧭</div>
                <div class="ch-wel-title">你好，我是你的<br><em>AI 求职教练</em></div>
                <div class="ch-wel-sub">
                    覆盖投递全流程：从岗位把关、简历改写，到面试演练和投递复盘。
                    <br>我会记住你的偏好，越用越懂你。试试下面这些，或直接说你的需求。
                </div>
                <div class="ch-caps">${caps.map(c => `<span class="ch-cap">${c}</span>`).join('')}</div>
                <div class="ch-suggests">
                    ${SUGGESTIONS.map(s => `
                        <button class="ch-sugg" data-q="${esc(s.q)}">
                            <span class="ch-sugg-ico">${s.icon}</span>
                            <span class="ch-sugg-txt">${esc(s.label)}</span>
                        </button>`).join('')}
                </div>
            </div>`;
        // 绑定建议
        thread.querySelectorAll('.ch-sugg').forEach(btn => {
            btn.addEventListener('click', () => {
                const input = root.querySelector('#ch-input');
                input.value = btn.dataset.q;
                if (input) { input.focus(); sendMessage(btn.dataset.q); }
            });
        });
    }

    function renderSkeleton() {
        return `
        <div class="ch-app">
            <aside class="ch-rail" id="ch-rail"></aside>
            <div class="ch-rail-backdrop" id="ch-rail-backdrop"></div>
            <section class="ch-main">
                <div class="ch-main-head" id="ch-main-head">
                    <div class="ch-status" id="ch-status"><span class="dot"></span><span id="ch-status-text">就绪</span></div>
                    <div class="ch-llm" id="ch-llm">
                        <span class="ch-llm-chip" id="ch-llm-chip" title="点击前往设置页配置 LLM" data-goto-settings>—</span>
                    </div>
                    <div class="ch-main-title" id="ch-main-title">${esc(state.currentTitle || '新的对话')}</div>
                    <div class="ch-clear" id="ch-clear" title="清空当前对话区">↺ 重新开始</div>
                </div>
                <div class="ch-thread"><div class="ch-thread-inner"></div><button class="ch-scroll-down" id="ch-scroll-down" title="回到底部" aria-label="回到底部"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></button></div>
                <div class="ch-composer">
                    <div class="ch-composer-inner">
                        <div class="ch-input-shell">
                            <textarea class="ch-input" id="ch-input" rows="1" placeholder="告诉我你想做什么…（回车发送，Shift+回车换行）"></textarea>
                            <button class="ch-send" id="ch-send" title="发送" aria-label="发送">
                                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                            </button>
                        </div>
                        <div class="ch-hint">Job Coach · 数据随对话自动持久化 · 敏感操作需你确认</div>
                    </div>
                </div>
            </section>
        </div>`;
    }

    function renderRail() {
        const rail = root.querySelector('#ch-rail');
        rail.innerHTML = `
            <div class="ch-rail-head">
                <div class="ch-rail-eyebrow">Conversations</div>
                <button class="ch-new-btn" id="ch-new-btn">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    新的对话
                </button>
            </div>
            <div class="ch-rail-list" id="ch-rail-list"></div>`;
        rail.querySelector('#ch-new-btn').addEventListener('click', newChat);
        rail.classList.add('mounted');
    }

    // ============ 交互绑定 ============

    function bindComposer() {
        const input = root.querySelector('#ch-input');
        const send = root.querySelector('#ch-send');

        const autoResize = () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 140) + 'px';
        };

        input.addEventListener('input', autoResize);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (state.thinking) { toggleStop(); return; }
                const v = input.value.trim();
                if (v) { input.value = ''; autoResize(); sendMessage(v); }
            }
        });

        send.addEventListener('click', () => {
            if (state.thinking) { toggleStop(); return; }
            const v = input.value.trim();
            if (v) { input.value = ''; autoResize(); sendMessage(v); }
        });

        // 移动端：会话栏开关
        const clearBtn = root.querySelector('#ch-clear');
        clearBtn.addEventListener('click', () => {
            if (state.thinking) { API.toast('正在回答中', 'info'); return; }
            newChat();
        });
    }

    function toggleStop() {
        if (!state.thinking || !state.abort) return;
        try { state.abort.abort(); } catch (e) {}
    }

    // ============ 剪贴板 / 复制 ============

    async function copyText(text) {
        try { await navigator.clipboard.writeText(text || ''); return true; }
        catch (e) {
            try {
                const ta = document.createElement('textarea');
                ta.value = text || '';
                document.body.appendChild(ta); ta.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(ta);
                return ok;
            } catch (e2) { return false; }
        }
    }

    function flashCopied(btn) {
        const orig = btn.textContent;
        btn.classList.add('copied');
        btn.textContent = '已复制';
        setTimeout(() => { btn.classList.remove('copied'); btn.textContent = orig; }, 1200);
    }

    async function bindThreadEvents() {
        const thread = root.querySelector('.ch-thread');
        thread.addEventListener('scroll', onThreadScroll, { passive: true });
        root.querySelector('#ch-scroll-down').addEventListener('click', () => scrollToBottom(true));

        // 代码块 / 消息操作条 —— 事件委托，适应流式动态插入
        root.querySelector('.ch-thread-inner').addEventListener('click', async (e) => {
            // 代码块复制
            const codeBtn = e.target.closest('.md-copy-btn');
            if (codeBtn) {
                const code = codeBtn.dataset.code || codeBtn.parentElement.nextElementSibling.querySelector('code')?.textContent;
                const ok = await copyText(code);
                if (ok) flashCopied(codeBtn);
                return;
            }
            // 复制整条回复
            const copyBtn = e.target.closest('[data-act-copy]');
            if (copyBtn) {
                const host = copyBtn.closest('.ch-msg.assistant');
                const textEl = host && host.querySelector('.ch-md-body');
                const text = MD.render ? '' : '';
                const ok = await copyText(rawTextOf(host));
                if (ok) flashCopied(copyBtn);
                return;
            }
            // 重新生成
            const regen = e.target.closest('[data-act-regen]');
            if (regen) { regenerate(regen.closest('.ch-msg.assistant')); return; }
        });
    }

    // 提取一条 assistant 消息的纯文本（去掉代码块复制按钮等内嵌 UI）
    function rawTextOf(assistantEl) {
        if (!assistantEl) return '';
        const textEl = assistantEl.querySelector('.ch-md-body');
        if (!textEl) return '';
        const clone = textEl.cloneNode(true);
        clone.querySelectorAll('.md-copy-btn').forEach(b => b.remove());
        // markdown 数据以纯文本形式缓存在 data-buffer（若有更准确）
        const buf = textEl.dataset.buffer;
        if (buf) return buf;
        return (clone.textContent || '').replace(/\s*\n\s*/g, '\n').trim();
    }

    // ============ 会话栏折叠（桌面端） ============

    function toggleRailCollapse() {
        state.railCollapsed = !state.railCollapsed;
        root.querySelector('.ch-app').classList.toggle('rail-closed', state.railCollapsed);
        try { localStorage.setItem('oc_chat_rail_closed', state.railCollapsed ? '1' : '0'); } catch (e) {}
        root.querySelector('#ch-rail-collapse').setAttribute('title', state.railCollapsed ? '展开会话栏' : '收起会话栏');
    }

    // ============ 消息操作条 ============

    function appendActionBar(assistantEl) {
        if (!assistantEl || assistantEl.querySelector('.ch-msg-actions')) return;
        const wrap = assistantEl.querySelector('.ch-bubble');
        if (!wrap) return;
        const bar = document.createElement('div');
        bar.className = 'ch-msg-actions';
        bar.innerHTML = `
            <button class="ch-act-btn" data-act-copy title="复制回复"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> 复制</button>
            <button class="ch-act-btn" data-act-regen title="重新生成"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> 重新生成</button>`;
        wrap.appendChild(bar);
    }

    // ============ 重新生成 ============

    async function regenerate(assistantEl) {
        if (!assistantEl || state.thinking) return;
        const thread = root.querySelector('.ch-thread-inner');
        const msgs = Array.from(thread.querySelectorAll('.ch-msg'));
        const idx = msgs.indexOf(assistantEl);
        // 找到本条 assistant 之前的最后一条 user 消息来重发
        let prompt = '';
        for (let i = idx - 1; i >= 0; i--) {
            if (msgs[i].classList.contains('user')) {
                prompt = msgs[i].querySelector('.ch-msg-pill')?.textContent || '';
                break;
            }
            if (msgs[i].classList.contains('assistant')) {
                // 跨过工具宿主；若已追溯到更早 user 则用最近的
            }
        }
        // 移除本条及之后的所有消息，重新生成
        let cursor = assistantEl;
        while (cursor) { const next = cursor.nextElementSibling; cursor.remove(); cursor = next; }
        if (prompt) runGeneration(prompt);
    }

    // ============ 追问 chips ============

    function appendFollowups(assistantEl) {
        const followups = [
            { ico: '🔄', label: '换个角度再说说' },
            { ico: '➕', label: '展开讲细一点' },
            { ico: '📌', label: '把它整理成清单' },
        ];
        const wrap = assistantEl.querySelector('.ch-bubble');
        if (!wrap || wrap.querySelector('.ch-chips')) return;
        const chips = document.createElement('div');
        chips.className = 'ch-chips';
        chips.innerHTML = followups.map(f =>
            `<button class="ch-chip" data-chip="${esc(f.label)}"><span class="ch-chip-ico">${f.ico}</span>${esc(f.label)}</button>`
        ).join('');
        wrap.appendChild(chips);
        chips.querySelectorAll('.ch-chip').forEach(c => c.addEventListener('click', () => sendMessage(c.dataset.chip)));
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        root.innerHTML = renderSkeleton();
        renderRail();
        bindComposer();
        renderWelcome();
        setBusy(false);
        await loadSessions();
        loadLlmStatus();
        refocusInput();
        bindThreadEvents();

        // LLM 状态 chip：点击前往设置页
        const llmChip = root.querySelector('#ch-llm-chip');
        if (llmChip) {
            llmChip.addEventListener('click', () => {
                global.location.hash = '#/settings';
            });
        }

        // 桌面端会话栏折叠按钮（顶栏）
        if (!root.querySelector('#ch-rail-collapse')) {
            const collapse = document.createElement('button');
            collapse.className = 'ch-rail-collapse';
            collapse.id = 'ch-rail-collapse';
            collapse.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><polyline points="3 6 9 12 3 18"/><polyline points="15 6 21 12 15 18"/></svg>';
            (root.querySelector('#ch-main-head') || document.body).appendChild(collapse);
            collapse.addEventListener('click', toggleRailCollapse);
        }
        // 恢复持久化的折叠状态（仅桌面端）
        try {
            const saved = localStorage.getItem('oc_chat_rail_closed') === '1';
            if (saved && window.innerWidth > 860) {
                state.railCollapsed = true;
                root.querySelector('.ch-app').classList.add('rail-closed');
                root.querySelector('#ch-rail-collapse').setAttribute('title', '展开会话栏');
            }
        } catch (e) {}

        // 顶部移动端侧栏开关（放右会话区头部）
        if (!root.querySelector('.ch-rail-toggle')) {
            const toggle = document.createElement('button');
            toggle.className = 'ch-rail-toggle';
            toggle.id = 'ch-rail-toggle';
            toggle.textContent = '☰';
            (root.querySelector('#ch-main-head') || document.body).appendChild(toggle);
        }
        root.querySelector('#ch-rail-toggle').style.display = 'none';
        if (window.innerWidth <= 860 && root.querySelector('#ch-rail-toggle')) {
            root.querySelector('#ch-rail-toggle').style.display = 'flex';
        }
        root.querySelector('#ch-rail-toggle').addEventListener('click', (e) => {
            e.stopPropagation();
            if (root.querySelector('.ch-rail-backdrop')) {
                root.querySelector('.ch-rail').classList.toggle('open');
                root.querySelector('.ch-rail-backdrop').classList.toggle('open');
            }
        });
        root.querySelector('#ch-rail-backdrop').addEventListener('click', () => {
            root.querySelector('.ch-rail').classList.remove('open');
            root.querySelector('#ch-rail-backdrop').classList.remove('open');
        });
    }

    function cleanup() {
        // 中止进行中的流
        if (state.abort) { try { state.abort.abort(); } catch (e) {} }
        state.abort = null;
        root = null;
    }

    global.OfferCabinViews = global.OfferCabinViews || {};
    global.OfferCabinViews.chat = { mount: mount, cleanup: cleanup, title: 'AI 求职助手' };
})(window);