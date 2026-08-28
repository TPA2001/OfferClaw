/**
 * 岗位分享视图 — 网申广场（用户互助分享岗位，一键跳转官网 / 一键加入看板）
 * 卡片流（城市/即将截止/搜索 + 排序）→ 详情面板 → 去官网投递 / 加入我的看板 / 点赞收藏举报
 * 安全：跳转统一走后端 redirect 接口（校验 + 计数），前端 window.open 新窗口
 */
(function (global) {
    'use strict';

    const API = global.OfferClawAPI;
    const esc = API.esc.bind(API);

    const CSS_ID = 'jobshares-styles';

    const state = {
        city: '',
        expiring: false,
        keyword: '',
        sort: 'newest',
        page: 1,
        items: [],
        total: 0,
        loading: false,
        error: null,
        // 详情
        current: null,
        detailOpen: false,
        adding: false,
        // 分享表单
        composerOpen: false,
        submitting: false,
        form: { company: '', position: '', apply_url: '', city: '', salary: '', deadline: '', description: '' },
        currentUser: null,
    };

    let root = null;

    // ============ CSS ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
.js-view { padding-bottom: 4rem; }
.js-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:1rem; }
.js-header h2 { font-family:var(--font-serif); font-size:1.25rem; font-weight:700; color:var(--ink); margin:0; }
.js-sub { color:var(--ink-soft); font-size:.85rem; margin-top:.2rem; }

.js-toolbar { display:flex; gap:.6rem; margin-bottom:1rem; flex-wrap:wrap; align-items:center; }
.js-input { flex:1; min-width:150px; }
.js-select { min-width:110px; }
.js-check { display:flex; align-items:center; gap:.3rem; font-size:.85rem; color:var(--ink-soft); cursor:pointer; white-space:nowrap; }

.js-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(250px, 1fr)); gap:.8rem; }
.js-card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem 1.1rem; cursor:pointer; transition:box-shadow .2s var(--ease); display:flex; flex-direction:column; gap:.35rem; }
.js-card:hover { box-shadow:var(--shadow-sm); border-color:var(--olive); }
.js-card-company { font-weight:600; color:var(--ink); font-size:1rem; }
.js-card-position { color:var(--ink-soft); font-size:.88rem; }
.js-card-tags { display:flex; gap:.4rem; flex-wrap:wrap; }
.js-tag { padding:.06rem .5rem; border-radius:999px; font-size:.74rem; background:var(--olive-soft); color:var(--olive); }
.js-tag.city { background:var(--st-interview-soft); color:var(--st-interview); }
.js-tag.salary { background:var(--st-offer-soft); color:var(--st-offer); }
.js-tag.deadline { background:#fef3c7; color:#92400e; }
.js-card-meta { display:flex; align-items:center; color:var(--ink-faint); font-size:.78rem; margin-top:auto; padding-top:.3rem; }
.js-card-stats { margin-left:auto; display:flex; gap:.6rem; }

.js-btn { padding:.4rem 1rem; border-radius:8px; border:1px solid var(--line); background:var(--card); color:var(--ink-soft); font-size:.85rem; cursor:pointer; transition:all .15s var(--ease); }
.js-btn:hover { border-color:var(--olive); color:var(--olive); }
.js-btn.active { background:var(--olive); border-color:var(--olive); color:#fff; }
.js-btn.danger { color:var(--danger); border-color:var(--danger); }
.js-btn.danger:hover { background:var(--danger); color:#fff; }
.js-btn:disabled { opacity:.5; cursor:not-allowed; }
.js-btn-primary { background:var(--olive); border-color:var(--olive); color:#fff; }
.js-btn-primary:hover { background:var(--olive-dark); color:#fff; }
.js-btn-green { background:var(--st-offer); border-color:var(--st-offer); color:#fff; }
.js-btn-green:hover { background:var(--st-offer-deep); color:#fff; }

.js-modal-mask { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:100; display:flex; align-items:center; justify-content:center; padding:1rem; }
.js-modal { background:var(--card); border-radius:14px; padding:1.4rem 1.6rem; width:100%; max-width:640px; max-height:88vh; overflow:auto; }
.js-modal h3 { font-size:1.05rem; font-weight:600; color:var(--ink); margin:0 0 1rem; }
.js-modal h4 { font-size:.95rem; font-weight:600; color:var(--ink); margin:1rem 0 .5rem; }
.js-field { margin-bottom:.9rem; }
.js-field label { display:block; font-size:.82rem; color:var(--ink-soft); margin-bottom:.3rem; }
.js-field input, .js-field textarea { width:100%; box-sizing:border-box; }
.js-field-row { display:grid; grid-template-columns:1fr 1fr; gap:.8rem; }
.js-detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; margin-bottom:1rem; }
.js-detail-item { background:var(--paper-light); border-radius:8px; padding:.6rem .9rem; }
.js-detail-item .k { font-size:.75rem; color:var(--ink-faint); }
.js-detail-item .v { font-size:.9rem; color:var(--ink); font-weight:500; word-break:break-all; }
.js-desc { background:var(--paper-light); border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; font-size:.9rem; color:var(--ink); white-space:pre-wrap; word-break:break-word; margin-bottom:1rem; }
.js-empty, .js-loading { text-align:center; color:var(--ink-faint); padding:2.5rem 0; }
.js-warn { font-size:.8rem; color:var(--danger); margin-top:.3rem; }
`;
        document.head.appendChild(style);
    }

    // ============ 渲染 ============

    function renderShell() {
        return `
<div class="js-view">
    <div class="js-header">
        <div>
            <h2>岗位分享</h2>
            <div class="js-sub">网申信息共享，看到好岗位直接收藏并一键加入看板</div>
        </div>
        <button class="js-btn js-btn-primary" data-act="open-composer">分享岗位</button>
    </div>
    <div id="js-root"></div>
</div>`;
    }

    function renderToolbar() {
        return `
<div class="js-toolbar">
    <input class="js-input" id="js-search" placeholder="搜索公司 / 岗位…" value="${esc(state.keyword)}">
    <input class="js-input" id="js-city" placeholder="城市（如 北京）" value="${esc(state.city)}" style="max-width:130px;">
    <label class="js-check"><input type="checkbox" id="js-expiring" ${state.expiring ? 'checked' : ''}> 即将截止</label>
    <select class="js-select" id="js-sort">
        <option value="newest" ${state.sort === 'newest' ? 'selected' : ''}>最新分享</option>
        <option value="deadline" ${state.sort === 'deadline' ? 'selected' : ''}>按截止时间</option>
        <option value="hot" ${state.sort === 'hot' ? 'selected' : ''}>最热</option>
    </select>
    <button class="js-btn" data-act="search">筛选</button>
</div>`;
    }

    function renderCard(j) {
        const deadlineTag = j.deadline ? deadlineLabel(j.deadline) : '';
        return `
<div class="js-card" data-id="${j.id}">
    <div class="js-card-company">${esc(j.company)}</div>
    <div class="js-card-position">${esc(j.position)}</div>
    <div class="js-card-tags">
        ${j.city ? `<span class="js-tag city">${esc(j.city)}</span>` : ''}
        ${j.salary ? `<span class="js-tag salary">${esc(j.salary)}</span>` : ''}
        ${deadlineTag ? `<span class="js-tag deadline">${deadlineTag}</span>` : ''}
    </div>
    <div class="js-card-meta">
        <span>${esc(j.author)}</span>
        <span class="js-card-stats">
            <span>👁 ${j.view_count}</span>
            <span>👍 ${j.like_count}</span>
            <span>📌 ${j.collect_count}</span>
        </span>
    </div>
</div>`;
    }

    function renderList() {
        if (state.loading) return '<div class="js-loading">加载中…</div>';
        if (state.error) return `<div class="js-empty">加载失败：${esc(state.error)}</div>`;
        if (!state.items.length) return '<div class="js-empty">还没有岗位分享，来分享第一个吧</div>';
        return `<div class="js-grid">${state.items.map(renderCard).join('')}</div>`;
    }

    function renderDetailModal() {
        if (!state.detailOpen || !state.current) return '';
        const j = state.current;
        const my = API.currentUser();
        const isAuthor = my && my.id === j.author_id;
        return `
<div class="js-modal-mask" data-act="close-detail">
    <div class="js-modal" onclick="event.stopPropagation()">
        <h3>${esc(j.company)} · ${esc(j.position)}</h3>
        <div class="js-detail-grid">
            ${j.city ? `<div class="js-detail-item"><div class="k">城市</div><div class="v">${esc(j.city)}</div></div>` : ''}
            ${j.salary ? `<div class="js-detail-item"><div class="k">薪资</div><div class="v">${esc(j.salary)}</div></div>` : ''}
            ${j.deadline ? `<div class="js-detail-item"><div class="k">截止</div><div class="v">${deadlineLabel(j.deadline)}（${new Date(j.deadline).toLocaleString('zh-CN')}）</div></div>` : ''}
            <div class="js-detail-item"><div class="k">分享者</div><div class="v">${esc(j.author)}</div></div>
        </div>
        ${j.description ? `<div class="js-desc">${esc(j.description)}</div>` : ''}
        <div class="js-field-row" style="margin-bottom:.9rem;">
            <button class="js-btn js-btn-green" data-act="goto">↗ 去官网投递</button>
            <button class="js-btn js-btn-primary" data-act="to-app" ${state.adding ? 'disabled' : ''}>${state.adding ? '加入中…' : '＋ 加入我的看板'}</button>
        </div>
        <div style="display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;">
            <button class="js-btn ${j.liked ? 'active' : ''}" data-act="like">👍 ${j.like_count}</button>
            <button class="js-btn ${j.collected ? 'active' : ''}" data-act="collect">收藏 ${j.collect_count}</button>
            <button class="js-btn" data-act="report">举报</button>
            ${isAuthor ? '<button class="js-btn" data-act="edit">编辑</button><button class="js-btn danger" data-act="expire">标记过期</button><button class="js-btn danger" data-act="delete">删除</button>' : ''}
            <span style="margin-left:auto;color:var(--ink-faint);font-size:.78rem;">${j.click_count} 人点击过官网</span>
        </div>
    </div>
</div>`;
    }

    function renderComposerModal() {
        if (!state.composerOpen) return '';
        const f = state.form;
        return `
<div class="js-modal-mask" data-act="close-composer">
    <div class="js-modal" onclick="event.stopPropagation()">
        <h3>${f.editId ? '编辑岗位分享' : '分享岗位'}</h3>
        <div class="js-field"><label>公司名 *</label><input id="js-f-company" maxlength="200" value="${esc(f.company)}" placeholder="如 腾讯"></div>
        <div class="js-field"><label>岗位名 *</label><input id="js-f-position" maxlength="200" value="${esc(f.position)}" placeholder="如 后端开发工程师"></div>
        <div class="js-field"><label>网申官网链接 *（http/https）</label><input id="js-f-url" maxlength="2048" value="${esc(f.apply_url)}" placeholder="https://careers.tencent.com/..."></div>
        <div class="js-field-row">
            <div class="js-field"><label>城市</label><input id="js-f-city" maxlength="50" value="${esc(f.city)}" placeholder="北京"></div>
            <div class="js-field"><label>薪资范围</label><input id="js-f-salary" maxlength="100" value="${esc(f.salary)}" placeholder="20-30k"></div>
        </div>
        <div class="js-field"><label>网申截止日期</label><input id="js-f-deadline" type="date" value="${esc(f.deadline || '')}"></div>
        <div class="js-field"><label>备注（内推码 / 岗位要求等）</label><textarea id="js-f-desc" rows="3" maxlength="2000" placeholder="选填">${esc(f.description)}</textarea></div>
        <div class="js-warn">请只分享官方网申链接，分享前请确认链接真实有效</div>
        <div style="display:flex;justify-content:flex-end;gap:.6rem;margin-top:1rem;">
            <button class="js-btn" data-act="close-composer">取消</button>
            <button class="js-btn js-btn-primary" data-act="submit-job" ${state.submitting ? 'disabled' : ''}>${state.submitting ? '提交中…' : '提交'}</button>
        </div>
    </div>
</div>`;
    }

    function render() {
        const mount = root.querySelector('#js-root');
        if (!mount) return;
        mount.innerHTML = renderToolbar() + renderList() + renderDetailModal() + renderComposerModal();
    }

    // ============ 数据 ============

    async function loadList() {
        state.loading = true;
        state.error = null;
        render();
        try {
            const params = { page: state.page, page_size: 20, sort: state.sort };
            if (state.city.trim()) params.city = state.city.trim();
            if (state.expiring) params.expiring = 'true';
            if (state.keyword.trim()) params.keyword = state.keyword.trim();
            const data = await API.community.listJobs(params);
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
            state.current = await API.community.getJob(id);
            state.detailOpen = true;
            render();
        } catch (e) {
            API.toast(e.message || '加载失败', 'error');
        }
    }

    // ============ 交互 ============

    function onRootClick(e) {
        const t = e.target;
        const act = t.dataset.act;
        const card = t.closest('.js-card');

        if (act === 'open-composer') {
            resetComposer();
            state.composerOpen = true;
            render();
            return;
        }
        if (act === 'close-composer') { state.composerOpen = false; render(); return; }
        if (act === 'close-detail') { state.detailOpen = false; render(); return; }
        if (act === 'submit-job') { submitJob(); return; }
        if (act === 'search') { state.page = 1; loadList(); return; }
        if (act === 'goto') { gotoOfficial(); return; }
        if (act === 'to-app') { addToApplication(); return; }
        if (act === 'like') { toggleReact('like'); return; }
        if (act === 'collect') { toggleReact('collect'); return; }
        if (act === 'report') { doReport(); return; }
        if (act === 'edit') { openComposerForEdit(); return; }
        if (act === 'expire') { doExpire(); return; }
        if (act === 'delete') { doDelete(); return; }

        if (card) openDetail(card.dataset.id);
    }

    function onRootInput(e) {
        const t = e.target;
        if (t.id === 'js-search') state.keyword = t.value;
        if (t.id === 'js-city') state.city = t.value;
        if (t.id === 'js-expiring') { state.expiring = t.checked; state.page = 1; loadList(); }
        if (t.id === 'js-sort') { state.sort = t.value; state.page = 1; loadList(); }
        const f = state.form;
        if (t.id === 'js-f-company') f.company = t.value;
        if (t.id === 'js-f-position') f.position = t.value;
        if (t.id === 'js-f-url') f.apply_url = t.value;
        if (t.id === 'js-f-city') f.city = t.value;
        if (t.id === 'js-f-salary') f.salary = t.value;
        if (t.id === 'js-f-deadline') f.deadline = t.value;
        if (t.id === 'js-f-desc') f.description = t.value;
    }

    function resetComposer() {
        state.form = { company: '', position: '', apply_url: '', city: '', salary: '', deadline: '', description: '', editId: null };
    }

    function openComposerForEdit() {
        const j = state.current;
        state.form = {
            editId: j.id,
            company: j.company,
            position: j.position,
            apply_url: j.apply_url,
            city: j.city || '',
            salary: j.salary || '',
            deadline: j.deadline ? new Date(j.deadline).toISOString().slice(0, 10) : '',
            description: j.description || '',
        };
        state.composerOpen = true;
        render();
    }

    async function submitJob() {
        const f = state.form;
        if (!f.company.trim()) return API.toast('请填写公司名', 'error');
        if (!f.position.trim()) return API.toast('请填写岗位名', 'error');
        if (!f.apply_url.trim()) return API.toast('请填写网申链接', 'error');
        state.submitting = true;
        render();
        const payload = {
            company: f.company.trim(),
            position: f.position.trim(),
            apply_url: f.apply_url.trim(),
            city: f.city.trim() || null,
            salary: f.salary.trim() || null,
            description: f.description.trim() || null,
        };
        if (f.deadline) payload.deadline = new Date(f.deadline + 'T23:59:59+08:00').toISOString();
        try {
            let data;
            if (f.editId) {
                data = await API.community.updateJob(f.editId, payload);
            } else {
                data = await API.community.createJob(payload);
            }
            API.toast(data.message || '提交成功');
            state.composerOpen = false;
            if (f.editId) {
                state.current = data;
                render();
            } else {
                loadList();
            }
        } catch (err) {
            API.toast(err.message || '提交失败', 'error');
        } finally {
            state.submitting = false;
            render();
        }
    }

    async function gotoOfficial() {
        const j = state.current;
        try {
            const data = await API.community.redirectJob(j.id);
            j.click_count += 1;
            render();
            const win = window.open(data.url, '_blank', 'noopener');
            if (!win) {
                API.toast('浏览器拦截了弹窗，请允许新窗口打开');
            }
        } catch (e) {
            API.toast(e.message || '链接不可用', 'error');
        }
    }

    async function addToApplication() {
        const j = state.current;
        state.adding = true;
        render();
        try {
            const data = await API.community.jobToApplication(j.id);
            if (data.created) {
                API.toast('已加入投递看板', 'success');
            } else {
                API.toast(data.message || '该岗位已在看板中', 'warning');
            }
        } catch (e) {
            API.toast(e.message || '加入失败', 'error');
        } finally {
            state.adding = false;
            render();
        }
    }

    async function toggleReact(action) {
        const j = state.current;
        try {
            const data = await API.community.react({
                target_type: 'jobshare', target_id: j.id, action, value: !(action === 'like' ? j.liked : j.collected),
            });
            j.liked = data.liked;
            j.collected = data.collected;
            j.like_count = data.like_count;
            j.collect_count = data.collect_count;
            render();
        } catch (e) {
            API.toast(e.message || '操作失败', 'error');
        }
    }

    async function doReport() {
        const j = state.current;
        const reason = prompt('请填写举报原因（选填）：', '');
        if (reason === null) return;
        try {
            const data = await API.community.report({
                target_type: 'jobshare', target_id: j.id, reason: reason || null,
            });
            API.toast(data.message || '已举报');
        } catch (e) {
            API.toast(e.message || '举报失败', 'error');
        }
    }

    async function doExpire() {
        if (!confirm('确定标记该岗位已过期吗？')) return;
        try {
            await API.community.expireJob(state.current.id);
            API.toast('已标记过期');
            state.detailOpen = false;
            loadList();
        } catch (e) {
            API.toast(e.message || '操作失败', 'error');
        }
    }

    async function doDelete() {
        if (!confirm('确定删除该岗位分享吗？此操作不可恢复。')) return;
        try {
            await API.community.deleteJob(state.current.id);
            API.toast('已删除');
            state.detailOpen = false;
            loadList();
        } catch (e) {
            API.toast(e.message || '删除失败', 'error');
        }
    }

    function deadlineLabel(iso) {
        const t = new Date(iso).getTime();
        if (isNaN(t)) return '';
        const days = Math.ceil((t - Date.now()) / 86400000);
        if (days < 0) return '已截止';
        if (days === 0) return '今天截止';
        if (days <= 7) return '剩 ' + days + ' 天';
        return '截止 ' + new Date(iso).toLocaleDateString('zh-CN');
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        state.currentUser = API.currentUser();
        root.innerHTML = renderShell();
        root.addEventListener('click', onRootClick);
        root.addEventListener('input', onRootInput);
        await loadList();
    }

    function cleanup() {
        root = null;
    }

    global.OfferClawViews = global.OfferClawViews || {};
    global.OfferClawViews.jobShares = { mount, cleanup, title: '岗位分享' };
})(window);
