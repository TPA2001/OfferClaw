/**
 * 社区广场视图 — 用户交流板块（简历优化/面试经验/Offer 抉择/求助/闲聊）
 * 帖子列表（分类 Tab + 排序 + 搜索 + 骨架屏）→ 详情（正文 + 点赞收藏 + 楼中楼评论 + 举报）
 * 设计：复用全局 Design System（.view-header/.tabs/.card/.btn/.form-field/.empty-card）
 * 安全：所有用户内容经 esc() 转义渲染，杜绝 XSS
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const esc = API.esc.bind(API);

    const CSS_ID = 'community-styles';

    // 板块定义（label + 语义色）
    const CATEGORIES = [
        { key: '', label: '全部', color: 'var(--olive)' },
        { key: 'resume', label: '简历优化', color: 'var(--st-applied)' },
        { key: 'interview', label: '面试经验', color: 'var(--st-interview)' },
        { key: 'offer', label: 'Offer 抉择', color: 'var(--st-offer)' },
        { key: 'help', label: '求职求助', color: 'var(--st-assessment)' },
        { key: 'chat', label: '闲聊', color: 'var(--ink-soft)' },
    ];
    const catColor = (key) => {
        const c = CATEGORIES.find(x => x.key === key);
        return c ? c.color : 'var(--olive)';
    };
    const catLabel = (key) => {
        const c = CATEGORIES.find(x => x.key === key);
        return c ? c.label : key || '';
    };

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
        current: null,           // 当前帖子
        comments: [],
        commentText: '',
        replyTo: null,
        composerOpen: false,
        form: { title: '', content: '', category: 'chat', editId: null },
        submitting: false,
    };

    let root = null;

    // ============ 局部样式（仅补充全局库未覆盖的细节） ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
/* 工具条：搜索 + 排序 */
.cm-toolbar { display:flex; gap:.7rem; margin-bottom:1.1rem; align-items:center; flex-wrap:wrap; }
.cm-search { position:relative; flex:1; min-width:200px; }
.cm-search svg { position:absolute; left:.7rem; top:50%; transform:translateY(-50%); color:var(--ink-faint); pointer-events:none; }
.cm-search input { width:100%; box-sizing:border-box; padding:.55rem .7rem .55rem 2.1rem; border:1px solid var(--line); border-radius:6px; font-size:.88rem; font-family:inherit; color:var(--ink); background:var(--paper-light); transition:all .2s var(--ease); }
.cm-search input:focus { outline:none; border-color:var(--olive); background:#fff; box-shadow:0 0 0 3px var(--olive-glow); }
.cm-toolbar select { padding:.55rem .7rem; border:1px solid var(--line); border-radius:6px; font-size:.88rem; font-family:inherit; color:var(--ink); background:var(--paper-light); cursor:pointer; }

/* 帖子卡片 */
.cm-list { display:flex; flex-direction:column; gap:.7rem; }
.cm-card { display:flex; align-items:stretch; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden; cursor:pointer; transition:box-shadow .2s var(--ease), transform .2s var(--ease), border-color .2s var(--ease); }
.cm-card:hover { box-shadow:var(--shadow-md); transform:translateY(-2px); border-color:var(--line-strong, var(--olive)); }
.cm-card-rail { width:4px; flex-shrink:0; }
.cm-card-body { flex:1; padding:1rem 1.2rem; min-width:0; }
.cm-card-title { font-weight:600; color:var(--ink); font-size:.98rem; margin-bottom:.4rem; display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }
.cm-card-title .cm-pin { padding:.08rem .55rem; border-radius:999px; font-size:.7rem; font-weight:500; background:#fef3c7; color:#92400e; }
.cm-card-meta { display:flex; align-items:center; gap:1rem; color:var(--ink-faint); font-size:.8rem; flex-wrap:wrap; }
.cm-avatar { width:22px; height:22px; border-radius:50%; background:var(--olive-soft); color:var(--olive); display:inline-flex; align-items:center; justify-content:center; font-size:.72rem; font-weight:600; margin-right:.35rem; vertical-align:middle; }
.cm-stats { margin-left:auto; display:flex; gap:1rem; align-items:center; }
.cm-stat { display:inline-flex; align-items:center; gap:.3rem; }
.cm-stat svg { color:var(--ink-ghost); }

/* 帖子详情 */
.cm-detail-card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1.5rem 1.6rem; animation:fadeInUp .3s var(--ease); }
.cm-detail-head { display:flex; align-items:center; gap:.7rem; margin-bottom:.5rem; }
.cm-detail-title { font-family:var(--font-serif); font-size:1.4rem; font-weight:700; color:var(--ink); margin:.2rem 0 .6rem; line-height:1.45; }
.cm-detail-body { color:var(--ink); line-height:2; white-space:pre-wrap; word-break:break-word; font-size:.93rem; }
.cm-review-banner { background:color-mix(in srgb, var(--danger) 6%, var(--card)); border:1px solid color-mix(in srgb, var(--danger) 35%, var(--line)); color:var(--danger); border-radius:8px; padding:.6rem .9rem; font-size:.83rem; margin-bottom:1rem; }
.cm-actions { display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; border-top:1px dashed var(--line); margin-top:1.2rem; padding-top:1rem; }

/* 点赞动画 */
.cm-btn-like.liked svg { animation:cmPop .35s var(--ease); }
@keyframes cmPop { 0%{transform:scale(1)} 40%{transform:scale(1.45)} 100%{transform:scale(1)} }

/* 评论 */
.cm-comments { margin-top:1.4rem; }
.cm-comments-head { font-size:1rem; font-weight:600; color:var(--ink); margin-bottom:.9rem; }
.cm-comment { display:flex; gap:.75rem; padding:.85rem 0; border-bottom:1px dashed var(--line); }
.cm-comment.reply { margin-left:2.4rem; }
.cm-comment-avatar { width:32px; height:32px; border-radius:50%; background:var(--olive-soft); color:var(--olive); display:flex; align-items:center; justify-content:center; font-size:.8rem; font-weight:600; flex-shrink:0; }
.cm-comment-body { flex:1; min-width:0; }
.cm-comment-meta { font-size:.78rem; color:var(--ink-faint); margin-bottom:.2rem; }
.cm-comment-text { font-size:.9rem; color:var(--ink); white-space:pre-wrap; word-break:break-word; }
.cm-comment-reply-btn { font-size:.78rem; color:var(--olive); background:none; border:none; cursor:pointer; padding:0; margin-top:.3rem; }
.cm-reply-hint { font-size:.8rem; color:var(--olive); margin-top:.35rem; }

/* 发帖弹窗（全局 .modal-overlay 仅含过渡，此处补齐定位与背景） */
.cm-view .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:200; display:flex; align-items:center; justify-content:center; padding:1rem; }
.cm-view .modal-overlay .modal { background:var(--card); border-radius:14px; padding:1.4rem 1.6rem; width:100%; max-width:560px; max-height:88vh; overflow:auto; }
.cm-modal-title { font-family:var(--font-serif); font-size:1.15rem; font-weight:700; color:var(--ink); margin-bottom:1.1rem; }
.cm-tip { font-size:.78rem; color:var(--ink-faint); margin-top:.5rem; }

/* 骨架屏 */
.cm-skeleton { display:flex; flex-direction:column; gap:.7rem; }
.cm-skeleton .skeleton-row { border-radius:10px; }

/* 入场动画 */
.cm-card { animation:fadeInUp .35s var(--ease) both; }
@keyframes fadeInUp { from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:translateY(0)} }

/* 页面头：文字 + 右侧操作按钮 */
.cm-view > .view-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; }
.cm-view > .view-header > div:first-child { flex:1; min-width:200px; }
`;
        document.head.appendChild(style);
    }

    // ============ 渲染 ============

    function renderShell() {
        return `
        <div class="view-container cm-view">
            <div class="view-header">
                <div>
                    <div class="header-eyebrow">COMMUNITY</div>
                    <h1>社区广场</h1>
                    <p>和求职者交流简历、面试与 Offer 经验</p>
                </div>
                <button class="btn btn-primary" data-act="open-composer">发布帖子</button>
            </div>
            <div id="cm-root"></div>
        </div>`;
    }

    function renderTabs() {
        return `
        <div class="tabs" id="cm-tabs">
            ${CATEGORIES.map(c => {
                const cnt = c.key === '' ? state.total : (c.key === state.category ? state.items.length : '');
                return `<button class="tab ${state.category === c.key ? 'active' : ''}" data-cat="${c.key}">
                    ${c.label}${cnt !== '' ? `<span class="tab-badge">${cnt}</span>` : ''}
                </button>`;
            }).join('')}
        </div>`;
    }

    function renderToolbar() {
        return `
        <div class="cm-toolbar">
            <div class="cm-search">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
                <input id="cm-search" placeholder="搜索标题 / 内容…" value="${esc(state.keyword)}" maxlength="50">
            </div>
            <select id="cm-sort">
                <option value="newest" ${state.sort === 'newest' ? 'selected' : ''}>最新发布</option>
                <option value="hot" ${state.sort === 'hot' ? 'selected' : ''}>最热</option>
            </select>
        </div>`;
    }

    function statIcon(kind) {
        if (kind === 'view') return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
        if (kind === 'like') return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
        return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    }

    function renderCard(p, idx) {
        return `
<div class="cm-card" data-id="${p.id}" style="animation-delay:${Math.min(idx * 45, 400)}ms">
    <div class="cm-card-rail" style="background:${catColor(p.category)}"></div>
    <div class="cm-card-body">
        <div class="cm-card-title">${p.is_pinned ? '<span class="cm-pin">置顶</span>' : ''}${esc(p.title)}</div>
        <div class="cm-card-meta">
            <span><span class="cm-avatar">${esc((p.author || '匿').slice(0, 1))}</span>${esc(p.author)}</span>
            <span>${timeAgo(p.created_at)}</span>
            <span class="cm-stats">
                <span class="cm-stat">${statIcon('view')}${p.view_count}</span>
                <span class="cm-stat">${statIcon('like')}${p.like_count}</span>
                <span class="cm-stat">${statIcon('comment')}${p.comment_count}</span>
            </span>
        </div>
    </div>
</div>`;
    }

    function renderSkeleton() {
        return `<div class="cm-skeleton">${[0, 1, 2].map(() =>
            '<div class="skeleton-row" style="height:84px"></div>').join('')}</div>`;
    }

    function renderList() {
        if (state.loading) return renderSkeleton();
        if (state.error) return `<div class="empty-card"><div class="empty-icon">⚠</div><p>加载失败：${esc(state.error)}</p></div>`;
        if (!state.items.length) return `<div class="empty-card"><div class="empty-icon">💬</div><p>还没有帖子，来发布第一条吧</p><p><button class="btn btn-primary btn-sm" data-act="open-composer">发布帖子</button></p></div>`;
        return `<div class="cm-list">${state.items.map(renderCard).join('')}</div>`;
    }

    function renderDetail() {
        const p = state.current;
        if (!p) return '';
        const my = API.currentUser();
        const isAuthor = my && my.id === p.author_id;
        return `
<div class="cm-detail-card">
    <button class="btn btn-ghost btn-sm" data-act="back">← 返回列表</button>
    <div style="margin-top:1rem;">
        <div class="cm-detail-head">
            <span class="tab-badge" style="background:${catColor(p.category)}22;color:${catColor(p.category)};padding:.15rem .65rem;border-radius:999px;font-size:.75rem;font-weight:500;">${catLabel(p.category)}</span>
            ${p.is_pinned ? '<span class="tab-badge" style="background:#fef3c7;color:#92400e;padding:.15rem .65rem;border-radius:999px;font-size:.75rem;">置顶</span>' : ''}
            <span class="text-faint" style="font-size:.8rem;">${esc(p.author)} · ${timeAgo(p.created_at)}</span>
        </div>
        <h2 class="cm-detail-title">${esc(p.title)}</h2>
        ${p.status === 'hidden' ? '<div class="cm-review-banner">内容审核中，通过后将对外可见。你可修改后重新提交审核。</div>' : ''}
        <div class="cm-detail-body">${esc(p.content)}</div>
        <div class="cm-actions">
            <button class="btn btn-sm cm-btn-like ${p.liked ? 'btn-primary' : 'btn-ghost'}" data-act="like">
                ${statIcon('like')} ${p.liked ? '已赞' : '点赞'} ${p.like_count}
            </button>
            <button class="btn btn-sm ${p.collected ? 'btn-primary' : 'btn-ghost'}" data-act="collect">收藏 ${p.collect_count}</button>
            <button class="btn btn-sm btn-ghost" data-act="report">举报</button>
            ${isAuthor ? '<button class="btn btn-sm btn-ghost" data-act="edit">编辑</button><button class="btn btn-sm btn-danger" data-act="delete">删除</button>' : ''}
        </div>
    </div>
    <div class="cm-comments">
        <div class="cm-comments-head">评论（${p.comment_count}）</div>
        <div class="card" style="padding:1rem;margin-bottom:1.2rem;">
            <textarea id="cm-comment-input" rows="2" maxlength="2000" placeholder="友善评论，理性发言…" style="width:100%;box-sizing:border-box;padding:.55rem .7rem;border:1px solid var(--line);border-radius:6px;font-size:.88rem;font-family:inherit;color:var(--ink);background:var(--paper-light);resize:vertical;">${esc(state.commentText)}</textarea>
            ${state.replyTo ? `<div class="cm-reply-hint">正在回复 @${esc(replyAuthorName())} <button class="btn btn-ghost btn-sm" data-act="cancel-reply">取消</button></div>` : ''}
            <div style="display:flex;justify-content:flex-end;margin-top:.5rem;">
                <button class="btn btn-primary btn-sm" data-act="comment">发表评论</button>
            </div>
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
        if (!state.comments.length) return '<div class="empty-card" style="padding:1.2rem;"><p>暂无评论，来抢沙发</p></div>';
        return state.comments.map(c => `
<div class="cm-comment ${c.parent_id ? 'reply' : ''}">
    <div class="cm-comment-avatar">${esc((c.author || '匿').slice(0, 1))}</div>
    <div class="cm-comment-body">
        <div class="cm-comment-meta">${esc(c.author)} · ${timeAgo(c.created_at)}</div>
        <div class="cm-comment-text">${esc(c.content)}</div>
        ${c.parent_id ? '' : `<button class="cm-comment-reply-btn" data-id="${c.id}">回复</button>`}
    </div>
</div>`).join('');
    }

    function renderComposerModal() {
        if (!state.composerOpen) return '';
        const f = state.form;
        return `
<div class="modal-overlay show" data-act="close-composer">
    <div class="modal">
        <div class="cm-modal-title">${f.editId ? '编辑帖子' : '发布帖子'}</div>
        <div class="form-field" style="margin-bottom:.9rem;"><label>标题 *</label>
            <input id="cm-f-title" maxlength="100" value="${esc(f.title)}" placeholder="一句话说清主题">
        </div>
        <div class="form-field" style="margin-bottom:.9rem;"><label>板块</label>
            <select id="cm-f-category">
                ${CATEGORIES.filter(c => c.key).map(c => `<option value="${c.key}" ${f.category === c.key ? 'selected' : ''}>${c.label}</option>`).join('')}
            </select>
        </div>
        <div class="form-field" style="margin-bottom:.9rem;"><label>内容 *</label>
            <textarea id="cm-f-content" rows="7" maxlength="5000" placeholder="详细描述…">${esc(f.content)}</textarea>
        </div>
        <div class="cm-tip">请遵守社区规范：不发布违法违规、广告营销或侵犯他人隐私的内容。</div>
        <div style="display:flex;justify-content:flex-end;gap:.6rem;margin-top:1rem;">
            <button class="btn btn-ghost" data-act="close-composer">取消</button>
            <button class="btn btn-primary" data-act="submit-post" ${state.submitting ? 'disabled' : ''}>${state.submitting ? '发布中…' : (f.editId ? '保存' : '发布')}</button>
        </div>
    </div>
</div>`;
    }

    function render() {
        const mount = root.querySelector('#cm-root');
        if (!mount) return;
        const content = state.view === 'detail'
            ? renderDetail()
            : renderTabs() + renderToolbar() + renderList();
        mount.innerHTML = content + renderComposerModal();
    }

    // ============ 数据 ============

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
        const t = e.target;
        const act = t.dataset.act;
        const card = t.closest('.cm-card');
        const tab = t.closest('.tab');

        if (act === 'open-composer') {
            state.form = { title: '', content: '', category: 'chat', editId: null };
            state.composerOpen = true;
            render();
            return;
        }
        if (act === 'close-composer') { state.composerOpen = false; render(); return; }
        if (act === 'submit-post') { submitPost(); return; }
        if (act === 'back') { state.view = 'list'; state.current = null; loadList(); return; }
        if (act === 'like') { toggleReact('like'); return; }
        if (act === 'collect') { toggleReact('collect'); return; }
        if (act === 'report') { doReport(); return; }
        if (act === 'edit') { openComposerForEdit(); return; }
        if (act === 'delete') { doDeletePost(); return; }
        if (act === 'comment') { submitComment(); return; }
        if (act === 'cancel-reply') { state.replyTo = null; render(); return; }

        if (tab && tab.dataset.cat !== undefined) {
            state.category = tab.dataset.cat;
            state.page = 1;
            loadList();
            return;
        }
        if (card) { openDetail(card.dataset.id); return; }
        if (t.classList.contains('cm-comment-reply-btn') && t.dataset.id) {
            state.replyTo = t.dataset.id;
            render();
            return;
        }
    }

    function onRootInput(e) {
        const t = e.target;
        if (t.id === 'cm-search') { state.keyword = t.value; }
        if (t.id === 'cm-sort') { state.sort = t.value; state.page = 1; loadList(); }
        if (t.id === 'cm-comment-input') state.commentText = t.value;
        if (t.id === 'cm-f-title') state.form.title = t.value;
        if (t.id === 'cm-f-content') state.form.content = t.value;
        if (t.id === 'cm-f-category') state.form.category = t.value;
    }

    function onKeydown(e) {
        if (e.key === 'Escape' && state.composerOpen) { state.composerOpen = false; render(); }
        // 搜索回车
        if (e.key === 'Enter' && e.target && e.target.id === 'cm-search') {
            state.page = 1;
            loadList();
        }
    }

    async function submitPost() {
        const title = state.form.title.trim();
        const content = state.form.content.trim();
        if (!title) return API.toast('请填写标题', 'error');
        if (!content) return API.toast('请填写内容', 'error');
        state.submitting = true;
        render();
        try {
            const payload = { title, content, category: state.form.category };
            const data = state.form.editId
                ? await API.community.updatePost(state.form.editId, payload)
                : await API.community.createPost(payload);
            state.composerOpen = false;
            API.toast(data.message || '保存成功');
            state.page = 1;
            loadList();
        } catch (err) {
            API.toast(err.message || '操作失败', 'error');
        } finally {
            state.submitting = false;
            render();
        }
    }

    function openComposerForEdit() {
        const p = state.current;
        state.form = { title: p.title, content: p.content, category: p.category, editId: p.id };
        state.composerOpen = true;
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
        const reason = prompt('请填写举报原因（选填）：', '');
        if (reason === null) return;
        try {
            const data = await API.community.report({
                target_type: 'post', target_id: state.current.id, reason: reason || null,
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
        // 清理上次可能残留的模态/详情状态（防止 cleanup 后重 mount 状态泄漏）
        state.composerOpen = false;
        state.view = 'list';
        state.current = null;
        state.comments = [];
        state.replyTo = null;
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
