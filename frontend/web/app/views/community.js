/**
 * 社区广场视图 — 用户交流板块（简历优化/面试经验/Offer 抉择/求助/闲聊）
 * 帖子列表（分类 Tab + 排序 + 搜索）→ 详情（正文 + 点赞收藏 + 楼中楼评论 + 举报）
 * 安全：所有用户内容经 esc() 转义渲染，杜绝 XSS
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const esc = API.esc.bind(API);

    const CSS_ID = 'community-styles';

    const CATEGORIES = [
        { key: '', label: '全部' },
        { key: 'resume', label: '简历优化' },
        { key: 'interview', label: '面试经验' },
        { key: 'offer', label: 'Offer 抉择' },
        { key: 'help', label: '求职求助' },
        { key: 'chat', label: '闲聊' },
    ];

    const state = {
        view: 'list',            // list | detail
        category: '',
        sort: 'newest',
        keyword: '',
        page: 1,
        items: [],
        total: 0,
        loading: false,
        error: null,
        // 详情
        current: null,           // 当前帖子
        comments: [],
        commentText: '',
        replyTo: null,           // 楼中楼回复目标评论 id
        // 表单
        composerOpen: false,
        formTitle: '',
        formContent: '',
        formCategory: 'chat',
        submitting: false,
        currentUser: null,
    };

    let root = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.cm-view { padding-bottom: 4rem; }
.cm-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1rem; }
.cm-header h2 { font-family:var(--font-serif); font-size:1.25rem; font-weight:700; color:var(--ink); margin:0; }
.cm-sub { color:var(--ink-soft); font-size:.85rem; margin-top:.2rem; }

.cm-tabs { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:1rem; }
.cm-tab { padding:.35rem .9rem; border-radius:999px; border:1px solid var(--line); background:var(--card); color:var(--ink-soft); font-size:.85rem; cursor:pointer; transition:all .15s var(--ease); }
.cm-tab:hover { border-color:var(--olive); color:var(--olive); }
.cm-tab.active { background:var(--olive); border-color:var(--olive); color:#fff; }

.cm-toolbar { display:flex; gap:.6rem; margin-bottom:1rem; flex-wrap:wrap; }
.cm-input { flex:1; min-width:180px; }
.cm-select { min-width:110px; }

.cm-card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; margin-bottom:.7rem; cursor:pointer; transition:box-shadow .2s var(--ease); }
.cm-card:hover { box-shadow:var(--shadow-sm); border-color:var(--olive); }
.cm-card-title { font-weight:600; color:var(--ink); font-size:.98rem; margin-bottom:.3rem; }
.cm-card-meta { display:flex; align-items:center; gap:.8rem; color:var(--ink-faint); font-size:.8rem; flex-wrap:wrap; }
.cm-badge { padding:.08rem .55rem; border-radius:999px; font-size:.75rem; background:var(--olive-soft); color:var(--olive); }
.cm-pin { background:#fef3c7; color:#92400e; }
.cm-stats { margin-left:auto; display:flex; gap:.7rem; }

.cm-detail-back { background:none; border:1px solid var(--line); border-radius:8px; padding:.35rem .8rem; color:var(--ink-soft); cursor:pointer; margin-bottom:1rem; }
.cm-detail-back:hover { color:var(--olive); border-color:var(--olive); }

.cm-detail-title { font-family:var(--font-serif); font-size:1.35rem; font-weight:700; color:var(--ink); margin:.2rem 0 .5rem; }
.cm-detail-body { color:var(--ink); line-height:1.9; white-space:pre-wrap; word-break:break-word; background:var(--paper-light); border:1px solid var(--line); border-radius:10px; padding:1.2rem 1.4rem; margin:1rem 0; }

.cm-action-row { display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; }
.cm-btn { padding:.4rem 1rem; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--ink-soft); font-size:.85rem; cursor:pointer; transition:all .15s var(--ease); }
.cm-btn:hover { border-color:var(--olive); color:var(--olive); }
.cm-btn.active { background:var(--olive); border-color:var(--olive); color:#fff; }
.cm-btn.danger { color:var(--danger); border-color:var(--danger); }
.cm-btn.danger:hover { background:var(--danger); color:#fff; }
.cm-btn:disabled { opacity:.5; cursor:not-allowed; }
.cm-btn-primary { background:var(--olive); border-color:var(--olive); color:#fff; }
.cm-btn-primary:hover { background:var(--olive-dark); color:#fff; }

.cm-comments { margin-top:1.6rem; }
.cm-comments h3 { font-size:1rem; font-weight:600; color:var(--ink); margin-bottom:.8rem; }
.cm-comment { display:flex; gap:.7rem; padding:.7rem 0; border-bottom:1px dashed var(--line-soft); }
.cm-comment.reply { margin-left:2.2rem; }
.cm-comment-avatar { width:30px; height:30px; border-radius:50%; background:var(--olive-soft); color:var(--olive); display:flex; align-items:center; justify-content:center; font-size:.78rem; flex-shrink:0; }
.cm-comment-body { flex:1; min-width:0; }
.cm-comment-meta { font-size:.78rem; color:var(--ink-faint); margin-bottom:.15rem; }
.cm-comment-text { font-size:.9rem; color:var(--ink); white-space:pre-wrap; word-break:break-word; }
.cm-comment-reply { font-size:.78rem; color:var(--olive); background:none; border:none; cursor:pointer; padding:0; margin-top:.3rem; }

.cm-composer { background:var(--paper-light); border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; margin-bottom:1rem; }
.cm-composer h3 { font-size:.95rem; font-weight:600; color:var(--ink); margin:0 0 .8rem; }
.cm-modal-mask { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:flex; align-items:center; justify-content:center; padding:1rem; }
.cm-modal { background:var(--card); border-radius:14px; padding:1.4rem 1.6rem; width:100%; max-width:560px; max-height:88vh; overflow:auto; }
.cm-modal h3 { font-size:1.05rem; font-weight:600; color:var(--ink); margin:0 0 1rem; }
.cm-field { margin-bottom:.9rem; }
.cm-field label { display:block; font-size:.82rem; color:var(--ink-soft); margin-bottom:.3rem; }
.cm-field input, .cm-field textarea, .cm-field select { width:100%; box-sizing:border-box; }
.cm-empty { text-align:center; color:var(--ink-faint); padding:2.5rem 0; }
.cm-loading { text-align:center; color:var(--ink-faint); padding:2rem 0; }
`;
        document.head.appendChild(style);
    }

    // ============ 渲染 ============

    function renderShell() {
        return `
<div class="cm-view">
    <div class="cm-header">
        <div>
            <h2>社区广场</h2>
            <div class="cm-sub">和求职者交流简历、面试与 Offer 经验</div>
        </div>
        <button class="cm-btn cm-btn-primary" data-act="open-composer">发布帖子</button>
    </div>
    <div id="cm-root"></div>
</div>`;
    }

    function renderTabs() {
        return `<div class="cm-tabs">${CATEGORIES.map(c =>
            `<button class="cm-tab ${state.category === c.key ? 'active' : ''}" data-cat="${c.key}">${c.label}</button>`
        ).join('')}</div>`;
    }

    function renderToolbar() {
        return `
<div class="cm-toolbar">
    <input class="cm-input" id="cm-search" placeholder="搜索标题 / 内容…" value="${esc(state.keyword)}">
    <select class="cm-select" id="cm-sort">
        <option value="newest" ${state.sort === 'newest' ? 'selected' : ''}>最新发布</option>
        <option value="hot" ${state.sort === 'hot' ? 'selected' : ''}>最热</option>
    </select>
    <button class="cm-btn" data-act="search">搜索</button>
</div>`;
    }

    function renderCard(p) {
        return `
<div class="cm-card" data-id="${p.id}">
    <div class="cm-card-title">${p.is_pinned ? '<span class="cm-badge cm-pin">置顶</span> ' : ''}${esc(p.title)}</div>
    <div class="cm-card-meta">
        <span class="cm-badge">${esc(p.category_label)}</span>
        <span>${esc(p.author)}</span>
        <span>${timeAgo(p.created_at)}</span>
        <span class="cm-stats">
            <span>👁 ${p.view_count}</span>
            <span>👍 ${p.like_count}</span>
            <span>💬 ${p.comment_count}</span>
        </span>
    </div>
</div>`;
    }

    function renderList() {
        if (state.loading) return '<div class="cm-loading">加载中…</div>';
        if (state.error) return `<div class="cm-empty">加载失败：${esc(state.error)}</div>`;
        if (!state.items.length) return '<div class="cm-empty">还没有帖子，来发布第一条吧</div>';
        return state.items.map(renderCard).join('');
    }

    function renderDetail() {
        const p = state.current;
        if (!p) return '';
        const my = API.currentUser();
        const isAuthor = my && my.id === p.author_id;
        return `
<div>
    <button class="cm-detail-back" data-act="back">← 返回列表</button>
    <div class="cm-badge">${esc(p.category_label)}</div>
    <div class="cm-detail-title">${p.is_pinned ? '<span class="cm-badge cm-pin">置顶</span> ' : ''}${esc(p.title)}</div>
    <div class="cm-card-meta" style="margin-bottom:.4rem;">
        <span>${esc(p.author)}</span><span>${timeAgo(p.created_at)}</span>
        <span>浏览 ${p.view_count}</span>
    </div>
    ${p.status === 'hidden' ? '<div class="cm-composer" style="border-color:var(--danger);"><b>内容审核中</b>，通过后将对外可见，你可在此修改后重新提交审核。</div>' : ''}
    <div class="cm-detail-body">${esc(p.content)}</div>
    <div class="cm-action-row">
        <button class="cm-btn ${p.liked ? 'active' : ''}" data-act="like">👍 ${p.like_count}</button>
        <button class="cm-btn ${p.collected ? 'active' : ''}" data-act="collect">收藏 ${p.collect_count}</button>
        <button class="cm-btn" data-act="report">举报</button>
        ${isAuthor ? '<button class="cm-btn" data-act="edit">编辑</button><button class="cm-btn danger" data-act="delete">删除</button>' : ''}
    </div>
    <div class="cm-comments">
        <h3>评论（${p.comment_count}）</h3>
        <div class="cm-composer" style="margin-bottom:1rem;">
            <textarea id="cm-comment-input" rows="2" placeholder="友善评论，理性发言…" style="width:100%;box-sizing:border-box;">${esc(state.commentText)}</textarea>
            ${state.replyTo ? '<div style="font-size:.8rem;color:var(--olive);margin-top:.3rem;">回复 @' + esc(replyAuthorName()) + ' <button class="cm-btn" data-act="cancel-reply" style="padding:.1rem .5rem;font-size:.75rem;">取消</button></div>' : ''}
            <div style="margin-top:.5rem;"><button class="cm-btn cm-btn-primary" data-act="comment">发表评论</button></div>
        </div>
        ${renderComments()}
    </div>
</div>`;
    }

    function replyAuthorName() {
        if (!state.replyTo) return '';
        const c = state.comments.find(x => x.id === state.replyTo);
        return c ? c.author : '';
    }

    function renderComments() {
        if (!state.comments.length) return '<div class="cm-empty" style="padding:1rem 0;">暂无评论</div>';
        return state.comments.map(c => `
<div class="cm-comment ${c.parent_id ? 'reply' : ''}" data-id="${c.id}">
    <div class="cm-comment-avatar">${esc((c.author || '匿').slice(0, 1))}</div>
    <div class="cm-comment-body">
        <div class="cm-comment-meta">${esc(c.author)} · ${timeAgo(c.created_at)}</div>
        <div class="cm-comment-text">${esc(c.content)}</div>
        ${c.parent_id ? '' : `<button class="cm-comment-reply" data-id="${c.id}">回复</button>`}
    </div>
</div>`).join('');
    }

    function renderComposerModal() {
        if (!state.composerOpen) return '';
        return `
<div class="cm-modal-mask" data-act="close-composer">
    <div class="cm-modal" onclick="event.stopPropagation()">
        <h3>发布帖子</h3>
        <div class="cm-field"><label>标题</label><input id="cm-f-title" maxlength="100" value="${esc(state.formTitle)}" placeholder="一句话说清主题"></div>
        <div class="cm-field"><label>板块</label>
            <select id="cm-f-category">${CATEGORIES.filter(c => c.key).map(c =>
                `<option value="${c.key}" ${state.formCategory === c.key ? 'selected' : ''}>${c.label}</option>`).join('')}
            </select></div>
        <div class="cm-field"><label>内容</label><textarea id="cm-f-content" rows="6" maxlength="5000" placeholder="详细描述…">${esc(state.formContent)}</textarea></div>
        <div class="cm-action-row" style="justify-content:flex-end;">
            <button class="cm-btn" data-act="close-composer">取消</button>
            <button class="cm-btn cm-btn-primary" data-act="submit-post" ${state.submitting ? 'disabled' : ''}>${state.submitting ? '发布中…' : '发布'}</button>
        </div>
    </div>
</div>`;
    }

    function render() {
        const content = state.view === 'detail'
            ? renderDetail()
            : renderTabs() + renderToolbar() + renderList();
        const mount = root.querySelector('#cm-root');
        if (mount) mount.innerHTML = content;
    }

    // ============ 数据加载 ============

    async function loadList() {
        state.loading = true;
        state.error = null;
        render();
        try {
            const params = { page: state.page, page_size: 20 };
            if (state.category) params.category = state.category;
            if (state.sort) params.sort = state.sort;
            if (state.keyword.trim()) params.keyword = state.keyword.trim();
            const data = await API.community.listPosts(params);
            state.items = data.items || [];
            state.total = data.total || 0;
        } catch (e) {
            state.error = e.message || '加载失败';
        } finally {
            state.loading = false;
            render();
        }
    }

    async function openDetail(id) {
        try {
            const post = await API.community.getPost(id);
            state.current = post;
            state.comments = [];
            state.replyTo = null;
            state.commentText = '';
            state.view = 'detail';
            render();
            const cdata = await API.community.listComments(id);
            state.comments = cdata.items || [];
            render();
        } catch (e) {
            API.toast(e.message || '加载失败', 'error');
        }
    }

    // ============ 交互 ============

    function onRootClick(e) {
        const target = e.target;
        const act = target.dataset.act;
        const card = target.closest('.cm-card');
        const tab = target.closest('.cm-tab');
        const cmt = target.closest('.cm-comment');

        if (act === 'open-composer') {
            state.composerOpen = true;
            state.formTitle = '';
            state.formContent = '';
            state.formCategory = 'chat';
            render();
            return;
        }
        if (act === 'close-composer') {
            state.composerOpen = false;
            render();
            return;
        }
        if (act === 'submit-post') { submitPost(); return; }
        if (act === 'search') {
            state.page = 1;
            loadList();
            return;
        }
        if (act === 'back') {
            state.view = 'list';
            state.current = null;
            loadList();
            return;
        }
        if (act === 'like') { toggleReact('like'); return; }
        if (act === 'collect') { toggleReact('collect'); return; }
        if (act === 'report') { doReport(); return; }
        if (act === 'edit') { openComposerForEdit(); return; }
        if (act === 'delete') { doDeletePost(); return; }
        if (act === 'comment') { submitComment(); return; }
        if (act === 'cancel-reply') {
            state.replyTo = null;
            render();
            return;
        }

        if (tab) {
            state.category = tab.dataset.cat;
            state.page = 1;
            loadList();
            return;
        }
        if (card) {
            openDetail(card.dataset.id);
            return;
        }
        if (cmt && target.dataset.id && target.classList.contains('cm-comment-reply')) {
            state.replyTo = target.dataset.id;
            render();
            return;
        }
    }

    function onRootInput(e) {
        const t = e.target;
        if (t.id === 'cm-search') state.keyword = t.value;
        if (t.id === 'cm-sort') { state.sort = t.value; state.page = 1; loadList(); }
        if (t.id === 'cm-comment-input') state.commentText = t.value;
        if (t.id === 'cm-f-title') state.formTitle = t.value;
        if (t.id === 'cm-f-content') state.formContent = t.value;
        if (t.id === 'cm-f-category') state.formCategory = t.value;
    }

    function onKeydown(e) {
        if (e.key === 'Escape' && state.composerOpen) {
            state.composerOpen = false;
            render();
        }
    }

    async function submitPost() {
        const title = state.formTitle.trim();
        const content = state.formContent.trim();
        if (!title) return API.toast('请填写标题', 'error');
        if (!content) return API.toast('请填写内容', 'error');
        state.submitting = true;
        render();
        try {
            const data = await API.community.createPost({
                title, content, category: state.formCategory,
            });
            state.composerOpen = false;
            API.toast(data.message || '发布成功');
            state.page = 1;
            loadList();
        } catch (err) {
            API.toast(err.message || '发布失败', 'error');
        } finally {
            state.submitting = false;
            render();
        }
    }

    function openComposerForEdit() {
        const p = state.current;
        state.composerOpen = true;
        state.formTitle = p.title;
        state.formContent = p.content;
        state.formCategory = p.category;
        render();
    }

    async function toggleReact(action) {
        const p = state.current;
        try {
            const data = await API.community.react({
                target_type: 'post', target_id: p.id, action, value: !(action === 'like' ? p.liked : p.collected),
            });
            p.liked = data.liked;
            p.collected = data.collected;
            p.like_count = data.like_count;
            p.collect_count = data.collect_count;
            render();
        } catch (e) {
            API.toast(e.message || '操作失败', 'error');
        }
    }

    async function doReport() {
        const p = state.current;
        const reason = prompt('请填写举报原因（选填）：', '');
        if (reason === null) return;
        try {
            const data = await API.community.report({
                target_type: 'post', target_id: p.id, reason: reason || null,
            });
            API.toast(data.message || '已举报');
        } catch (e) {
            API.toast(e.message || '举报失败', 'error');
        }
    }

    async function doDeletePost() {
        if (!confirm('确定删除该帖子吗？此操作不可恢复。')) return;
        try {
            await API.community.deletePost(state.current.id);
            API.toast('已删除');
            state.view = 'list';
            loadList();
        } catch (e) {
            API.toast(e.message || '删除失败', 'error');
        }
    }

    async function submitComment() {
        const content = state.commentText.trim();
        if (!content) return API.toast('请输入评论内容', 'error');
        try {
            await API.community.createComment(state.current.id, {
                content,
                parent_id: state.replyTo || null,
            });
            state.commentText = '';
            state.replyTo = null;
            state.current.comment_count += 1;
            const cdata = await API.community.listComments(state.current.id);
            state.comments = cdata.items || [];
            render();
        } catch (e) {
            API.toast(e.message || '评论失败', 'error');
        }
    }

    function timeAgo(iso) {
        if (!iso) return '';
        const t = new Date(iso).getTime();
        if (isNaN(t)) return '';
        const diff = (Date.now() - t) / 1000;
        if (diff < 60) return '刚刚';
        if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
        if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
        if (diff < 86400 * 30) return Math.floor(diff / 86400) + ' 天前';
        return new Date(iso).toLocaleDateString('zh-CN');
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        state.currentUser = API.currentUser();
        root.innerHTML = renderShell();
        root.addEventListener('click', onRootClick);
        root.addEventListener('input', onRootInput);
        document.addEventListener('keydown', onKeydown);
        await loadList();
    }

    function cleanup() {
        document.removeEventListener('keydown', onKeydown);
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.community = { mount, cleanup, title: '社区广场' };
})(window);
