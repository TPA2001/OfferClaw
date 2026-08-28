/**
 * 岗位分享视图 — 网申广场（用户互助分享岗位，一键跳转官网 / 一键加入看板）
 * 卡片流（城市/即将截止/搜索 + 排序 + 骨架屏）→ 详情面板 → 去官网投递 / 加入看板
 * 设计：复用全局 Design System（.view-header/.card/.btn/.form-field/.empty-card）
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
        current: null,
        detailOpen: false,
        adding: false,
        composerOpen: false,
        submitting: false,
        form: { company: '', position: '', apply_url: '', city: '', salary: '', deadline: '', description: '', editId: null },
    };

    let root = null;

    // ============ 局部样式（补充全局库未覆盖的细节） ============

    function injectStyles() {
        if (document.getElementById(CSS_ID)) return;
        const style = document.createElement('style');
        style.id = CSS_ID;
        style.textContent = `
/* 筛选条 */
.js-filterbar { display:flex; gap:.7rem; margin-bottom:1.1rem; flex-wrap:wrap; align-items:center; }
.js-filterbar input, .js-filterbar select { padding:.55rem .7rem; border:1px solid var(--line); border-radius:6px; font-size:.88rem; font-family:inherit; color:var(--ink); background:var(--paper-light); transition:all .2s var(--ease); }
.js-filterbar input:focus, .js-filterbar select:focus { outline:none; border-color:var(--olive); background:#fff; box-shadow:0 0 0 3px var(--olive-glow); }
.js-search { position:relative; flex:1; min-width:180px; }
.js-search svg { position:absolute; left:.7rem; top:50%; transform:translateY(-50%); color:var(--ink-faint); pointer-events:none; }
.js-search input { width:100%; box-sizing:border-box; padding-left:2.1rem; }
.js-city { width:120px; }
.js-check { display:flex; align-items:center; gap:.4rem; font-size:.85rem; color:var(--ink-soft); cursor:pointer; white-space:nowrap; user-select:none; }
.js-check input { accent-color:var(--olive); }

/* 岗位卡片网格 */
.js-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(255px, 1fr)); gap:.8rem; }
.js-card { display:flex; flex-direction:column; gap:.45rem; background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1.1rem 1.2rem; cursor:pointer; transition:box-shadow .2s var(--ease), transform .2s var(--ease), border-color .2s var(--ease); animation:fadeInUp .35s var(--ease) both; }
.js-card:hover { box-shadow:var(--shadow-md); transform:translateY(-2px); border-color:var(--olive); }
.js-card-company { font-weight:600; color:var(--ink); font-size:1.02rem; display:flex; align-items:center; gap:.4rem; }
.js-card-company .co-dot { width:8px; height:8px; border-radius:2px; background:var(--olive); flex-shrink:0; }
.js-card-position { color:var(--ink-soft); font-size:.88rem; }
.js-tags { display:flex; gap:.35rem; flex-wrap:wrap; margin-top:.1rem; }
.js-tag { padding:.08rem .55rem; border-radius:999px; font-size:.74rem; font-weight:500; }
.js-tag.city { background:color-mix(in srgb, var(--st-interview) 10%, var(--card)); color:var(--st-interview); }
.js-tag.salary { background:color-mix(in srgb, var(--st-offer) 10%, var(--card)); color:var(--st-offer); }
.js-tag.deadline { background:#fef3c7; color:#92400e; }
.js-tag.expired { background:color-mix(in srgb, var(--danger) 9%, var(--card)); color:var(--danger); }
.js-card-footer { display:flex; align-items:center; color:var(--ink-faint); font-size:.78rem; margin-top:auto; padding-top:.45rem; border-top:1px dashed var(--line); }
.js-card-stats { margin-left:auto; display:flex; gap:.7rem; }
.js-stat { display:inline-flex; align-items:center; gap:.3rem; }
.js-stat svg { color:var(--ink-ghost); }

/* 详情弹窗 */
.js-modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.35); z-index:200; display:flex; align-items:center; justify-content:center; padding:1rem; }
.js-modal { background:var(--card); border-radius:14px; padding:1.5rem 1.7rem; width:100%; max-width:660px; max-height:88vh; overflow:auto; animation:fadeInUp .3s var(--ease); }
.js-modal-title { font-family:var(--font-serif); font-size:1.2rem; font-weight:700; color:var(--ink); margin-bottom:.2rem; }
.js-modal-sub { color:var(--ink-soft); font-size:.85rem; margin-bottom:1rem; }
.js-detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; margin-bottom:1rem; }
.js-detail-item { background:var(--paper-light); border:1px solid var(--line); border-radius:8px; padding:.55rem .85rem; }
.js-detail-item .k { font-size:.74rem; color:var(--ink-faint); margin-bottom:.15rem; }
.js-detail-item .v { font-size:.9rem; color:var(--ink); font-weight:500; word-break:break-all; }
.js-desc { background:var(--paper-light); border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; font-size:.9rem; color:var(--ink); white-space:pre-wrap; word-break:break-word; margin-bottom:1rem; }
.js-modal-actions { display:flex; gap:.6rem; margin-bottom:.9rem; flex-wrap:wrap; }
.js-main-actions { display:flex; gap:.6rem; flex-wrap:wrap; margin-bottom:.9rem; }
.js-sub-actions { display:flex; gap:.6rem; flex-wrap:wrap; align-items:center; border-top:1px dashed var(--line); padding-top:.9rem; }
.js-click-hint { margin-left:auto; color:var(--ink-faint); font-size:.78rem; }
.js-warn { font-size:.78rem; color:var(--danger); margin-top:.4rem; }
.js-tip { font-size:.78rem; color:var(--ink-faint); margin-top:.5rem; }
.js-btn-green { background:var(--st-offer); border-color:var(--st-offer); color:#fff; }
.js-btn-green:hover { background:color-mix(in srgb, var(--st-offer) 82%, var(--ink)); color:#fff; transform:translateY(-1px); box-shadow:0 4px 12px color-mix(in srgb, var(--st-offer) 30%, transparent); }

/* 页面头：文字 + 右侧操作按钮 */
.js-view > .view-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem; }
.js-view > .view-header > div:first-child { flex:1; min-width:200px; }

/* 骨架屏 */
.js-skeleton { display:grid; grid-template-columns:repeat(auto-fill, minmax(255px, 1fr)); gap:.8rem; }
.js-skeleton .skeleton-row { border-radius:10px; }

@keyframes fadeInUp { from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:translateY(0)} }
`;
        document.head.appendChild(style);
    }

    // ============ 渲染 ============

    function renderShell() {
        return `
        <div class="view-container js-view">
            <div class="view-header">
                <div>
                    <div class="header-eyebrow">JOB SHARES</div>
                    <h1>岗位分享</h1>
                    <p>网申信息共享，看到好岗位一键加入投递看板</p>
                </div>
                <button class="btn btn-primary" data-act="open-composer">分享岗位</button>
            </div>
            <div id="js-root"></div>
        </div>`;
    }

    function renderFilterbar() {
        return `
        <div class="js-filterbar">
            <div class="js-search">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg>
                <input id="js-search" placeholder="搜索公司 / 岗位…" value="${esc(state.keyword)}" maxlength="50">
            </div>
            <input class="js-city" id="js-city" placeholder="城市" value="${esc(state.city)}" maxlength="50">
            <label class="js-check"><input type="checkbox" id="js-expiring" ${state.expiring ? 'checked' : ''}> 即将截止</label>
            <select id="js-sort">
                <option value="newest" ${state.sort === 'newest' ? 'selected' : ''}>最新分享</option>
                <option value="deadline" ${state.sort === 'deadline' ? 'selected' : ''}>按截止时间</option>
                <option value="hot" ${state.sort === 'hot' ? 'selected' : ''}>最热</option>
            </select>
        </div>`;
    }

    function statIcon(kind) {
        if (kind === 'view') return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
        if (kind === 'like') return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
        return '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    }

    function renderCard(j, idx) {
        const tags = [];
        if (j.city) tags.push(`<span class="js-tag city">${esc(j.city)}</span>`);
        if (j.salary) tags.push(`<span class="js-tag salary">${esc(j.salary)}</span>`);
        if (j.deadline) {
            const d = deadlineInfo(j.deadline);
            tags.push(`<span class="js-tag ${d.expired ? 'expired' : 'deadline'}">${d.label}</span>`);
        }
        return `
<div class="js-card" data-id="${j.id}" style="animation-delay:${Math.min(idx * 45, 400)}ms">
    <div class="js-card-company"><span class="co-dot"></span>${esc(j.company)}</div>
    <div class="js-card-position">${esc(j.position)}</div>
    <div class="js-tags">${tags.join('')}</div>
    <div class="js-card-footer">
        <span>${esc(j.author)}</span>
        <span class="js-card-stats">
            <span class="js-stat">${statIcon('view')}${j.view_count}</span>
            <span class="js-stat">${statIcon('like')}${j.like_count}</span>
            <span class="js-stat">${statIcon('collect')}${j.collect_count}</span>
        </span>
    </div>
</div>`;
    }

    function renderSkeleton() {
        return `<div class="js-skeleton">${[0, 1, 2, 3].map(() =>
            '<div class="skeleton-row" style="height:132px"></div>').join('')}</div>`;
    }

    function renderList() {
        if (state.loading) return renderSkeleton();
        if (state.error) return `<div class="empty-card"><div class="empty-icon">⚠</div><p>加载失败：${esc(state.error)}</p></div>`;
        if (!state.items.length) return `<div class="empty-card"><div class="empty-icon">📣</div><p>还没有岗位分享，来分享第一个吧</p><p><button class="btn btn-primary btn-sm" data-act="open-composer">分享岗位</button></p></div>`;
        return `<div class="js-grid">${state.items.map(renderCard).join('')}</div>`;
    }

    function renderDetailModal() {
        if (!state.detailOpen || !state.current) return '';
        const j = state.current;
        const my = API.currentUser();
        const isAuthor = my && my.id === j.author_id;
        return `
<div class="js-modal-overlay" data-act="close-detail">
    <div class="js-modal">
        <div class="js-modal-title">${esc(j.company)} · ${esc(j.position)}</div>
        <div class="js-modal-sub">由 ${esc(j.author)} 分享</div>
        <div class="js-detail-grid">
            ${j.city ? `<div class="js-detail-item"><div class="k">城市</div><div class="v">${esc(j.city)}</div></div>` : ''}
            ${j.salary ? `<div class="js-detail-item"><div class="k">薪资范围</div><div class="v">${esc(j.salary)}</div></div>` : ''}
            ${j.deadline ? `<div class="js-detail-item"><div class="k">网申截止</div><div class="v">${new Date(j.deadline).toLocaleDateString('zh-CN')}（${deadlineInfo(j.deadline).label}）</div></div>` : ''}
            <div class="js-detail-item"><div class="k">浏览量</div><div class="v">${j.view_count} 次</div></div>
        </div>
        ${j.description ? `<div class="js-desc">${esc(j.description)}</div>` : ''}
        <div class="js-main-actions">
            <button class="btn js-btn-green" data-act="goto">↗ 去官网投递</button>
            <button class="btn btn-primary" data-act="to-app" ${state.adding ? 'disabled' : ''}>${state.adding ? '加入中…' : '＋ 加入我的看板'}</button>
        </div>
        <div class="js-sub-actions">
            <button class="btn btn-sm ${j.liked ? 'btn-primary' : 'btn-ghost'}" data-act="like">${statIcon('like')} ${j.liked ? '已赞' : '点赞'} ${j.like_count}</button>
            <button class="btn btn-sm ${j.collected ? 'btn-primary' : 'btn-ghost'}" data-act="collect">收藏 ${j.collect_count}</button>
            <button class="btn btn-sm btn-ghost" data-act="report">举报</button>
            ${isAuthor ? '<button class="btn btn-sm btn-ghost" data-act="edit">编辑</button><button class="btn btn-sm btn-ghost" data-act="expire">标记过期</button><button class="btn btn-sm btn-danger" data-act="delete">删除</button>' : ''}
            <span class="js-click-hint">${j.click_count} 人已跳转官网</span>
        </div>
    </div>
</div>`;
    }

    function renderComposerModal() {
        if (!state.composerOpen) return '';
        const f = state.form;
        return `
<div class="js-modal-overlay" data-act="close-composer">
    <div class="js-modal">
        <div class="js-modal-title">${f.editId ? '编辑岗位分享' : '分享岗位'}</div>
        <div class="js-modal-sub">分享官方网申链接，帮助更多求职者</div>
        <div class="form-grid">
            <div class="form-field"><label>公司名 *</label><input id="js-f-company" maxlength="200" value="${esc(f.company)}" placeholder="如 腾讯"></div>
            <div class="form-field"><label>岗位名 *</label><input id="js-f-position" maxlength="200" value="${esc(f.position)}" placeholder="如 后端开发工程师"></div>
            <div class="form-field full"><label>网申官网链接 *（http/https）</label><input id="js-f-url" maxlength="2048" value="${esc(f.apply_url)}" placeholder="https://careers.tencent.com/..."></div>
            <div class="form-field"><label>城市</label><input id="js-f-city" maxlength="50" value="${esc(f.city)}" placeholder="北京"></div>
            <div class="form-field"><label>薪资范围</label><input id="js-f-salary" maxlength="100" value="${esc(f.salary)}" placeholder="20-30k"></div>
            <div class="form-field"><label>网申截止日期</label><input id="js-f-deadline" type="date" value="${esc(f.deadline || '')}"></div>
            <div class="form-field full"><label>备注（内推码 / 岗位要求等）</label><textarea id="js-f-desc" rows="3" maxlength="2000" placeholder="选填">${esc(f.description)}</textarea></div>
        </div>
        <div class="js-warn">请只分享官方网申链接，分享前请确认链接真实有效</div>
        <div class="js-tip">分享的岗位将同步参与社区内容审核</div>
        <div style="display:flex;justify-content:flex-end;gap:.6rem;margin-top:1rem;">
            <button class="btn btn-ghost" data-act="close-composer">取消</button>
            <button class="btn btn-primary" data-act="submit-job" ${state.submitting ? 'disabled' : ''}>${state.submitting ? '提交中…' : '提交'}</button>
        </div>
    </div>
</div>`;
    }

    function render() {
        const mount = root.querySelector('#js-root');
        if (!mount) return;
        mount.innerHTML = renderFilterbar() + renderList() + renderDetailModal() + renderComposerModal();
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
            state.form = { company: '', position: '', apply_url: '', city: '', salary: '', deadline: '', description: '', editId: null };
            state.composerOpen = true;
            render();
            return;
        }
        if (act === 'close-composer') { state.composerOpen = false; render(); return; }
        if (act === 'close-detail') { state.detailOpen = false; render(); return; }
        if (act === 'submit-job') { submitJob(); return; }
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

    function onKeydown(e) {
        if (e.key === 'Escape') {
            if (state.composerOpen) { state.composerOpen = false; render(); }
            else if (state.detailOpen) { state.detailOpen = false; render(); }
        }
        if (e.key === 'Enter' && e.target && (e.target.id === 'js-search' || e.target.id === 'js-city')) {
            state.page = 1;
            loadList();
        }
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
            if (!win) API.toast('浏览器拦截了弹窗，请允许新窗口打开');
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
            if (data.created) API.toast('已加入投递看板', 'success');
            else API.toast(data.message || '该岗位已在看板中', 'warning');
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
        const reason = prompt('请填写举报原因（选填）：', '');
        if (reason === null) return;
        try {
            const data = await API.community.report({
                target_type: 'jobshare', target_id: state.current.id, reason: reason || null,
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

    /** 截止信息：{ label, expired }，本地时区精确计算 */
    function deadlineInfo(iso) {
        const t = new Date(iso).getTime();
        if (isNaN(t)) return { label: '', expired: false };
        const days = Math.ceil((t - Date.now()) / 86400000);
        if (days < 0) return { label: '已截止', expired: true };
        if (days === 0) return { label: '今天截止', expired: false };
        if (days <= 7) return { label: '剩 ' + days + ' 天', expired: false };
        return { label: '截止 ' + new Date(iso).toLocaleDateString('zh-CN'), expired: false };
    }

    // ============ 挂载 / 清理 ============

    async function mount(container) {
        root = container;
        injectStyles();
        // 清理上次可能残留的模态/详情状态（防止 cleanup 后重 mount 状态泄漏）
        state.detailOpen = false;
        state.current = null;
        state.composerOpen = false;
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
    global.OfferClawViews.jobShares = { mount, cleanup, title: '岗位分享' };
})(window);
