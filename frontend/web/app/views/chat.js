/**
 * Chat 视图 — ChatGPT 式聊天主界面
 * 左侧会话列表 + 右侧消息流 + 输入区
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const MD = global.OfferClawMarkdown;
    const Motion = global.OfferClawMotion;

    // 会话状态
    let sessions = [];
    let currentSessionId = null;
    let isStreaming = false;
    let pendingConfirm = null;
    let abortController = null;

    // DOM 引用
    let root, sidebarList, chatArea, inputEl, sendBtn, newChatBtn;

    /**
     * 渲染视图骨架
     */
    function renderSkeleton() {
        return `
        <div class="chat-app">
            <aside class="chat-sidebar">
                <div class="sidebar-header">
                    <button class="btn-new-chat" id="btn-new-chat">
                        <span class="ico">+</span>
                        <span>新建对话</span>
                    </button>
                </div>
                <div class="sidebar-search">
                    <input type="text" id="session-search" placeholder="搜索对话..." class="search-input">
                </div>
                <div class="sidebar-list" id="session-list"></div>
                <div class="sidebar-footer">
                    <div class="user-card">
                        <div class="user-avatar">U</div>
                        <div class="user-info">
                            <div class="user-name">OfferClaw 用户</div>
                            <div class="user-status">在线</div>
                        </div>
                    </div>
                </div>
            </aside>
            <main class="chat-main">
                <div class="chat-toolbar">
                    <div class="session-title" id="session-title">新对话</div>
                    <div class="toolbar-actions">
                        <button class="icon-btn" id="btn-rename" title="重命名">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button class="icon-btn" id="btn-delete-session" title="删除对话">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                    </div>
                </div>
                <div class="chat-messages" id="chat-messages"></div>
                <div class="chat-input-area">
                    <div class="input-wrapper">
                        <textarea id="chat-input" class="chat-input" placeholder="输入消息，Enter 发送，Shift+Enter 换行..." rows="1"></textarea>
                        <button class="btn-send" id="btn-send" disabled>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                        </button>
                    </div>
                    <div class="input-hint">
                        <span>Agent 可调用 28 个工具</span>
                        <span class="dot">·</span>
                        <a href="#/settings" class="hint-link">配置模型</a>
                    </div>
                </div>
            </main>
        </div>
        `;
    }

    /**
     * 渲染空状态
     */
    function renderEmpty() {
        return `
        <div class="chat-empty">
            <div class="empty-logo">
                <div class="logo-mark">OC</div>
            </div>
            <h2 class="empty-title">OfferClaw Agent</h2>
            <p class="empty-subtitle">你的求职 AI 助手，能管理投递、分析岗位、生成简历、智能填表</p>
            <div class="suggestion-grid">
                <button class="suggestion-card" data-prompt="帮我看看当前的投递看板，有什么需要跟进的？">
                    <div class="sug-icon">📊</div>
                    <div class="sug-text">
                        <div class="sug-title">查看投递看板</div>
                        <div class="sug-desc">分析跟进提醒与统计数据</div>
                    </div>
                </button>
                <button class="suggestion-card" data-prompt="帮我分析这个岗位 https://www.zhipin.com/job/xxx 是否值得投递">
                    <div class="sug-icon">🎯</div>
                    <div class="sug-text">
                        <div class="sug-title">分析岗位</div>
                        <div class="sug-desc">JD 提取 + 真实性验证 + 匹配评分</div>
                    </div>
                </button>
                <button class="suggestion-card" data-prompt="根据我的画像生成一份针对后端工程师的简历">
                    <div class="sug-icon">📄</div>
                    <div class="sug-text">
                        <div class="sug-title">生成简历</div>
                        <div class="sug-desc">基于画像匹配岗位生成</div>
                    </div>
                </button>
                <button class="suggestion-card" data-prompt="帮我做一次面试复盘，我刚面试完字节跳动">
                    <div class="sug-icon">🎤</div>
                    <div class="sug-text">
                        <div class="sug-title">面试复盘</div>
                        <div class="sug-desc">LLM 辅助分析面试表现</div>
                    </div>
                </button>
            </div>
        </div>
        `;
    }

    /**
     * 加载会话列表
     */
    async function loadSessions() {
        try {
            const data = await API.get('/agent/sessions');
            sessions = Array.isArray(data) ? data : (data?.sessions || []);
            renderSessionList();
        } catch (e) {
            console.warn('加载会话失败:', e);
            sessions = [];
            renderSessionList();
        }
    }

    /**
     * 渲染会话列表
     */
    function renderSessionList(filter) {
        if (!sidebarList) return;
        let list = sessions;
        if (filter) {
            const f = filter.toLowerCase();
            list = sessions.filter(s => (s.title || s.session_id || '').toLowerCase().includes(f));
        }

        if (list.length === 0) {
            sidebarList.innerHTML = '<div class="empty-sessions">' +
                (filter ? '没有匹配的对话' : '暂无对话<br><span>点击「新建对话」开始</span>') +
                '</div>';
            return;
        }

        sidebarList.innerHTML = list.map(s => {
            const isActive = s.session_id === currentSessionId;
            const title = API.esc(s.title || '新对话');
            const time = formatTime(s.updated_at || s.created_at);
            const preview = API.esc(s.last_message || s.preview || '点击查看');
            return `
            <div class="session-item ${isActive ? 'active' : ''}" data-id="${s.session_id}">
                <div class="session-item-main">
                    <div class="session-item-title">${title}</div>
                    <div class="session-item-preview">${preview}</div>
                </div>
                <div class="session-item-time">${time}</div>
            </div>
            `;
        }).join('');
    }

    /**
     * 格式化时间
     */
    function formatTime(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        const now = new Date();
        const diff = now - d;
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
        if (diff < 604800000) return Math.floor(diff / 86400000) + '天前';
        return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
    }

    /**
     * 选择会话
     */
    async function selectSession(sessionId) {
        if (isStreaming) {
            API.toast('请等待当前回复完成', 'warn');
            return;
        }
        currentSessionId = sessionId;
        renderSessionList();

        // 更新标题
        const s = sessions.find(x => x.session_id === sessionId);
        if (s) {
            document.getElementById('session-title').textContent = s.title || '新对话';
        }

        try {
            const data = await API.get('/agent/sessions/' + sessionId);
            renderMessages(data?.messages || []);
        } catch (e) {
            API.toast('加载会话失败: ' + e.message, 'error');
            renderMessages([]);
        }
    }

    /**
     * 渲染消息列表
     */
    function renderMessages(messages) {
        if (!chatArea) return;
        if (!messages || messages.length === 0) {
            chatArea.innerHTML = renderEmpty();
            bindSuggestions();
            return;
        }

        chatArea.innerHTML = '';
        messages.forEach(msg => {
            appendMessage(msg.role, msg.content, { animate: false });
            // 渲染工具调用历史
            if (msg.tool_calls) {
                msg.tool_calls.forEach(tc => {
                    appendToolEvent(tc.name, tc.result, { animate: false });
                });
            }
        });
        scrollToBottom();
    }

    /**
     * 追加消息
     */
    function appendMessage(role, content, opts = {}) {
        const { animate = true } = opts;
        const wrapper = document.createElement('div');
        wrapper.className = 'msg msg-' + role;
        if (animate) wrapper.classList.add('msg-enter');

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'OC';

        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble';
        if (role === 'user') {
            bubble.textContent = content;
        } else {
            bubble.innerHTML = MD.render(content);
            bubble.classList.add('md-content');
        }

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
        chatArea.appendChild(wrapper);

        if (animate) {
            requestAnimationFrame(() => wrapper.classList.remove('msg-enter'));
        }
        return bubble;
    }

    /**
     * 追加工具事件
     */
    function appendToolEvent(name, result, opts = {}) {
        const { animate = true } = opts;
        const wrapper = document.createElement('div');
        wrapper.className = 'tool-event';
        if (animate) wrapper.classList.add('msg-enter');

        const success = result?.success !== false;
        const icon = success ? '✓' : '✗';
        const iconClass = success ? 'tool-ok' : 'tool-fail';

        wrapper.innerHTML = `
            <div class="tool-icon ${iconClass}">${icon}</div>
            <div class="tool-body">
                <div class="tool-name">${API.esc(name)}</div>
                <div class="tool-detail">${formatToolResult(result)}</div>
            </div>
        `;
        chatArea.appendChild(wrapper);

        if (animate) {
            requestAnimationFrame(() => wrapper.classList.remove('msg-enter'));
        }
        scrollToBottom();
    }

    /**
     * 格式化工具结果
     */
    function formatToolResult(result) {
        if (!result) return '';
        if (typeof result === 'string') return API.esc(result);
        if (result.error) return API.esc(result.error);
        if (result.message) return API.esc(result.message);
        if (result.summary) return API.esc(result.summary);
        if (result.data) {
            if (typeof result.data === 'string') return API.esc(result.data);
            return API.esc(JSON.stringify(result.data).slice(0, 200));
        }
        return API.esc(JSON.stringify(result).slice(0, 200));
    }

    /**
     * 追加确认卡片
     */
    function appendConfirmCard(actionId, message) {
        const wrapper = document.createElement('div');
        wrapper.className = 'confirm-card';
        wrapper.innerHTML = `
            <div class="confirm-icon">⚠</div>
            <div class="confirm-body">
                <div class="confirm-title">需要确认</div>
                <div class="confirm-message">${API.esc(message || 'Agent 请求执行敏感操作，是否允许？')}</div>
                <div class="confirm-actions">
                    <button class="btn btn-primary btn-sm" data-action="approve">允许执行</button>
                    <button class="btn btn-ghost btn-sm" data-action="reject">拒绝</button>
                </div>
            </div>
        `;
        chatArea.appendChild(wrapper);
        scrollToBottom();

        pendingConfirm = { actionId, wrapper };
        wrapper.querySelector('[data-action="approve"]').onclick = () => handleConfirm(true);
        wrapper.querySelector('[data-action="reject"]').onclick = () => handleConfirm(false);
    }

    /**
     * 处理确认
     */
    async function handleConfirm(approved) {
        if (!pendingConfirm) return;
        const { actionId, wrapper } = pendingConfirm;
        pendingConfirm = null;

        wrapper.innerHTML = '<div class="confirm-result">' +
            (approved ? '✓ 已允许' : '✗ 已拒绝') + '</div>';

        try {
            isStreaming = true;
            updateStreamingUI(true);
            const bubble = appendMessage('assistant', '');
            let contentBuffer = '';

            await API.stream('/agent/confirm', {
                action_id: actionId,
                approved: approved,
                session_id: currentSessionId,
            }, (evt) => {
                handleStreamEvent(evt, bubble, content => { contentBuffer = content; });
            });

            if (!contentBuffer) {
                bubble.innerHTML = MD.render(approved ? '已执行操作。' : '操作已取消。');
            }
        } catch (e) {
            API.toast('确认失败: ' + e.message, 'error');
        } finally {
            isStreaming = false;
            updateStreamingUI(false);
            await loadSessions();
        }
    }

    /**
     * 绑定建议卡片
     */
    function bindSuggestions() {
        chatArea.querySelectorAll('.suggestion-card').forEach(card => {
            card.onclick = () => {
                const prompt = card.dataset.prompt;
                if (inputEl) {
                    inputEl.value = prompt;
                    autoResize();
                    inputEl.focus();
                }
            };
        });
    }

    /**
     * 显示 typing 指示器
     */
    function showTyping() {
        const wrapper = document.createElement('div');
        wrapper.className = 'msg msg-assistant msg-enter typing-indicator';
        wrapper.id = 'typing-indicator';
        wrapper.innerHTML = `
            <div class="msg-avatar">OC</div>
            <div class="msg-bubble">
                <div class="typing-dots">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatArea.appendChild(wrapper);
        scrollToBottom();
    }

    /**
     * 移除 typing 指示器
     */
    function hideTyping() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }

    /**
     * 处理流式事件
     */
    function handleStreamEvent(evt, bubble, onContentUpdate) {
        let contentBuffer = '';
        switch (evt.type) {
            case 'content_delta':
                hideTyping();
                contentBuffer += evt.delta;
                bubble.innerHTML = MD.render(contentBuffer);
                onContentUpdate(contentBuffer);
                scrollToBottom();
                break;
            case 'tool_call_start':
                hideTyping();
                // 可选：显示工具开始调用
                break;
            case 'tool_result':
                appendToolEvent(evt.tool_name || evt.name, evt.result);
                break;
            case 'navigate':
                // Agent 请求跳转页面
                handleNavigate(evt.target, evt.params);
                break;
            case 'confirm_required':
                appendConfirmCard(evt.action_id, evt.message);
                break;
            case 'done':
                hideTyping();
                if (evt.session_id) {
                    currentSessionId = evt.session_id;
                }
                if (!bubble.innerHTML) {
                    bubble.innerHTML = MD.render(evt.content || '（无内容）');
                }
                break;
            case 'error':
                hideTyping();
                bubble.innerHTML = '<span class="msg-error">⚠ ' + API.esc(evt.message || '未知错误') + '</span>';
                break;
        }
    }

    /**
     * 处理 Agent 跳转请求
     */
    function handleNavigate(target, params) {
        const validRoutes = ['/kanban', '/profile', '/jobs', '/smart-fill', '/interview', '/settings'];
        if (validRoutes.includes(target)) {
            // 在消息中显示跳转提示
            const notice = document.createElement('div');
            notice.className = 'navigate-card';
            const routeName = {
                '/kanban': '投递看板',
                '/profile': '简历画像',
                '/jobs': '岗位搜索',
                '/smart-fill': '智能填表',
                '/interview': '面试复盘',
                '/settings': '设置',
            }[target] || target;
            notice.innerHTML = `
                <div class="nav-icon">→</div>
                <div class="nav-body">
                    <div class="nav-text">正在跳转到「${routeName}」</div>
                    <button class="btn btn-ghost btn-sm" onclick="window.location.hash='#${target}${params ? '?' + params : ''}'">立即前往</button>
                </div>
            `;
            chatArea.appendChild(notice);
            scrollToBottom();

            // 自动跳转（延迟 1.5 秒）
            setTimeout(() => {
                global.OfferClawRouter.navigate(target, params || {});
            }, 1500);
        }
    }

    /**
     * 发送消息
     */
    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || isStreaming) return;

        // 如果没有会话，先创建
        if (!currentSessionId) {
            await createNewSession();
        }

        // 显示用户消息
        appendMessage('user', text);
        inputEl.value = '';
        autoResize();
        updateSendButton();

        // 显示 typing
        showTyping();

        isStreaming = true;
        updateStreamingUI(true);

        // 准备 assistant 气泡
        const bubble = appendMessage('assistant', '');
        let contentBuffer = '';

        try {
            await API.stream('/agent/chat', {
                message: text,
                session_id: currentSessionId,
            }, (evt) => {
                handleStreamEvent(evt, bubble, content => { contentBuffer = content; });
            });

            if (!contentBuffer && !bubble.innerHTML) {
                bubble.innerHTML = MD.render('（Agent 未返回内容）');
            }
        } catch (e) {
            hideTyping();
            if (e.name === 'AbortError') {
                bubble.innerHTML = '<span class="msg-aborted">已停止</span>';
            } else {
                bubble.innerHTML = '<span class="msg-error">⚠ ' + API.esc(e.message) + '</span>';
            }
        } finally {
            isStreaming = false;
            updateStreamingUI(false);
            // 刷新会话列表（标题/预览可能更新）
            await loadSessions();
        }
    }

    /**
     * 创建新会话
     */
    async function createNewSession() {
        // 先清空当前界面，用户发送第一条消息后后端会自动创建 session
        currentSessionId = null;
        chatArea.innerHTML = renderEmpty();
        bindSuggestions();
        document.getElementById('session-title').textContent = '新对话';
        renderSessionList();
        inputEl.focus();
    }

    /**
     * 重命名会话
     */
    async function renameSession() {
        if (!currentSessionId) {
            API.toast('请先选择一个对话', 'warn');
            return;
        }
        const titleEl = document.getElementById('session-title');
        const oldTitle = titleEl.textContent;
        const input = document.createElement('input');
        input.type = 'text';
        input.value = oldTitle;
        input.className = 'title-edit-input';
        titleEl.replaceWith(input);
        input.focus();
        input.select();

        const commit = async () => {
            const newTitle = input.value.trim() || oldTitle;
            try {
                await API.patch('/agent/sessions/' + currentSessionId, { title: newTitle });
                const titleDiv = document.createElement('div');
                titleDiv.className = 'session-title';
                titleDiv.id = 'session-title';
                titleDiv.textContent = newTitle;
                input.replaceWith(titleDiv);
                await loadSessions();
                API.toast('已重命名', 'success');
            } catch (e) {
                API.toast('重命名失败: ' + e.message, 'error');
                const titleDiv = document.createElement('div');
                titleDiv.className = 'session-title';
                titleDiv.id = 'session-title';
                titleDiv.textContent = oldTitle;
                input.replaceWith(titleDiv);
            }
        };

        input.onblur = commit;
        input.onkeydown = (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            if (e.key === 'Escape') { input.value = oldTitle; input.blur(); }
        };
    }

    /**
     * 删除当前会话
     */
    async function deleteSession() {
        if (!currentSessionId) {
            API.toast('请先选择一个对话', 'warn');
            return;
        }
        if (!confirm('确定删除这个对话？此操作不可撤销。')) return;
        try {
            await API.del('/agent/sessions/' + currentSessionId);
            sessions = sessions.filter(s => s.session_id !== currentSessionId);
            currentSessionId = null;
            await createNewSession();
            renderSessionList();
            API.toast('已删除', 'success');
        } catch (e) {
            API.toast('删除失败: ' + e.message, 'error');
        }
    }

    /**
     * 自动调整输入框高度
     */
    function autoResize() {
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px';
    }

    /**
     * 更新发送按钮状态
     */
    function updateSendButton() {
        const hasText = inputEl.value.trim().length > 0;
        sendBtn.disabled = !hasText && !isStreaming;
        sendBtn.classList.toggle('streaming', isStreaming);
    }

    /**
     * 更新流式状态 UI
     */
    function updateStreamingUI(streaming) {
        sendBtn.disabled = !streaming && !inputEl.value.trim();
        if (streaming) {
            sendBtn.classList.add('streaming');
            sendBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
        } else {
            sendBtn.classList.remove('streaming');
            sendBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
        }
    }

    /**
     * 滚动到底部
     */
    function scrollToBottom() {
        requestAnimationFrame(() => {
            chatArea.scrollTop = chatArea.scrollHeight;
        });
    }

    /**
     * 绑定事件
     */
    function bindEvents() {
        newChatBtn = document.getElementById('btn-new-chat');
        sidebarList = document.getElementById('session-list');
        chatArea = document.getElementById('chat-messages');
        inputEl = document.getElementById('chat-input');
        sendBtn = document.getElementById('btn-send');

        // 新建对话
        newChatBtn.onclick = createNewSession;

        // 会话列表点击
        sidebarList.addEventListener('click', (e) => {
            const item = e.target.closest('.session-item');
            if (item) selectSession(item.dataset.id);
        });

        // 搜索
        const searchEl = document.getElementById('session-search');
        if (searchEl) {
            searchEl.oninput = () => renderSessionList(searchEl.value);
        }

        // 输入框
        inputEl.addEventListener('input', () => {
            autoResize();
            updateSendButton();
        });
        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (isStreaming) return;
                sendMessage();
            }
        });

        // 发送按钮
        sendBtn.addEventListener('click', () => {
            if (isStreaming) {
                // 流式中点击 = 停止（目前后端不支持中断，仅 UI 标记）
                API.toast('后端暂不支持中断流式', 'warn');
            } else {
                sendMessage();
            }
        });

        // 工具栏
        document.getElementById('btn-rename').onclick = renameSession;
        document.getElementById('btn-delete-session').onclick = deleteSession;
    }

    /**
     * 挂载视图
     */
    async function mount(container) {
        container.innerHTML = renderSkeleton();
        bindEvents();

        // 加载会话列表
        await loadSessions();

        // 默认显示空状态
        chatArea.innerHTML = renderEmpty();
        bindSuggestions();

        // 如果 URL 带了 session_id 参数，自动选中
        const { params } = global.OfferClawRouter.parseHash();
        if (params.session_id) {
            await selectSession(params.session_id);
        }

        inputEl.focus();
    }

    /**
     * 清理
     */
    function cleanup() {
        if (abortController) {
            abortController.abort();
        }
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.chat = { mount, cleanup, title: '对话' };
})(window);
