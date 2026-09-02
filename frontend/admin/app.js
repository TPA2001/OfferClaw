/**
 * OfferCabin 管理后台主控制器
 *
 * 轻量 SPA：登录卡 ↔ 面板；侧栏 tab 切换；各页 render 表格 + 操作按钮。
 * 设计系统复用主站 main.css（.app-shell/.app-topbar/.app-nav/.toast 等）。
 */
(function (global) {
    'use strict';

    const API = global.AdminAPI;
    const esc = API.esc;

    let currentTab = 'dashboard';
    let adminUser = null;
    // 各 tab 的分页/过滤状态
    const pageState = {
        users: { page: 1, q: '', role: '', status: '' },
        reports: { page: 1, status: 'pending' },
        posts: { page: 1, status: '' },
        jobshares: { page: 1, status: '' },
        audit: { page: 1, action: '' },
    };

    // ============ 工具 ============
    function $(id) { return document.getElementById(id); }
    function qs(sel, root) { return (root || document).querySelector(sel); }
    function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

    function badge(text, cls) {
        return '<span class="badge ' + (cls || '') + '">' + esc(text) + '</span>';
    }

    function statusBadge(status) {
        const map = { normal: '', pinned: 'pinned', hidden: 'hidden', deleted: 'deleted', expired: 'deleted' };
        return badge(status, map[status] || '');
    }

    function fmtDate(s) {
        if (!s) return '-';
        try { return new Date(s).toLocaleString('zh-CN', { hour12: false }); } catch (e) { return s; }
    }

    function pager(total, page, page_size, onNav) {
        const pages = Math.max(1, Math.ceil(total / page_size));
        const out = document.createElement('div');
        out.className = 'pager';
        const prev = document.createElement('button');
        prev.className = 'btn'; prev.textContent = '上一页'; prev.disabled = page <= 1;
        const next = document.createElement('button');
        next.className = 'btn'; next.textContent = '下一页'; next.disabled = page >= pages;
        const info = document.createElement('span');
        info.textContent = `第 ${page} / ${pages} 页 · 共 ${total} 条`;
        prev.onclick = () => onNav(page - 1);
        next.onclick = () => onNav(page + 1);
        out.appendChild(prev); out.appendChild(next); out.appendChild(info);
        return out;
    }

    async function confirmDialog(msg) {
        return global.confirm(msg);
    }

    async function withLoading(mount, promise) {
        mount.innerHTML = '<div class="loading-state">加载中…</div>';
        try { return await promise; }
        catch (e) {
            mount.innerHTML = '<div class="empty-state">' + esc(e.message || '加载失败') + '</div>';
            throw e;
        }
    }

    // ============ 启动 ============
    function showLogin(reason) {
        $('panel-shell').style.display = 'none';
        $('login-wrap').style.display = 'flex';
        API.setToken('');
        $('login-error').textContent = reason ? '登录已失效，请重新登录' : '';
        $('login-account').focus();
    }

    function showPanel() {
        $('login-wrap').style.display = 'none';
        $('panel-shell').style.display = '';
        if (adminUser) {
            $('admin-name').textContent = adminUser.username;
            $('admin-avatar').textContent = (adminUser.username || 'A').slice(0, 1).toUpperCase();
        }
    }

    global.onAdminAuthFail = function () { showLogin(true); };

    async function bootstrap() {
        // 应用主题（复用主站 localStorage）
        try {
            if (global.OfferCabinTheme && global.OfferCabinTheme.apply) {
                global.OfferCabinTheme.apply(global.OfferCabinTheme.current());
            } else {
                // 未引入 config.js，最小化应用主题暗色
                const t = localStorage.getItem('oc_theme') || 'paper';
                const dark = { ink: 1, forest: 1, ocean: 1 };
                document.documentElement.setAttribute('data-theme', t);
                document.body && document.body.classList.toggle('is-dark', !!dark[t]);
            }
        } catch (e) {}

        if (!API.isLoggedIn()) { showLogin(false); return; }
        try {
            adminUser = await API.me();
            showPanel();
            switchTab('dashboard');
        } catch (e) {
            showLogin(true);
        }
    }

    // ============ 登录 ============
    function bindLogin() {
        $('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const account = $('login-account').value.trim();
            const password = $('login-password').value;
            const errEl = $('login-error');
            const btn = $('login-btn');
            errEl.textContent = ''; btn.disabled = true; btn.textContent = '登录中…';
            try {
                const data = await API.login(account, password);
                API.setToken(data.token);
                adminUser = data.user;
                showPanel();
                switchTab('dashboard');
                API.toast('登录成功', 'success');
            } catch (err) {
                errEl.textContent = err.message || '登录失败';
            } finally {
                btn.disabled = false; btn.textContent = '登录';
            }
        });
    }

    function bindLogout() {
        $('btn-logout').addEventListener('click', () => {
            API.setToken('');
            adminUser = null;
            showLogin(false);
            API.toast('已退出登录', 'info');
        });
    }

    // ============ 导航 ============
    function bindNav() {
        qsa('.nav-item[data-tab]').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.tab));
        });
    }

    function switchTab(tab) {
        const mount = $('view-mount');
        // 同一 tab 内刷新（操作后重载/翻页）时保留滚动位置，切 tab 才回到顶部。
        // 渲染是异步的（表格数据回来后才撑高内容），因此连续几帧恢复，
        // 直到滚动位置生效或超过上限（约 1s）为止。
        const keepScroll = (tab === currentTab) ? mount.scrollTop : 0;
        currentTab = tab;
        qsa('.nav-item[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        mount.innerHTML = '';
        if (keepScroll > 0) {
            let tries = 0;
            const restore = () => {
                mount.scrollTop = keepScroll;
                if (mount.scrollTop < keepScroll && ++tries < 60) requestAnimationFrame(restore);
            };
            requestAnimationFrame(restore);
        }
        const renderer = TABS[tab];
        if (renderer) renderer(mount);
    }

    // ============ Tab: 仪表盘 ============
    async function tabDashboard(mount) {
        mount.innerHTML = '<div class="admin-view"><h1 class="admin-view-title">仪表盘</h1><div class="loading-state">加载中…</div></div>';
        const view = qs('.admin-view', mount);
        try {
            const s = await API.stats();
            const cards = [
                { label: '用户总数', value: s.users.total, sub: `活跃 ${s.users.active} · 管理员 ${s.users.admins}` },
                { label: '帖子', value: s.posts.normal + s.posts.pinned + s.posts.hidden, sub: `正常 ${s.posts.normal} · 置顶 ${s.posts.pinned} · 隐藏 ${s.posts.hidden} · 删除 ${s.posts.deleted}` },
                { label: '岗位分享', value: s.job_shares.normal + s.job_shares.hidden, sub: `正常 ${s.job_shares.normal} · 隐藏 ${s.job_shares.hidden}` },
                { label: '待处理举报', value: s.reports.pending, sub: `已处理 ${s.reports.handled}` },
            ];
            const grid = document.createElement('div');
            grid.className = 'stat-grid';
            cards.forEach(c => {
                const card = document.createElement('div');
                card.className = 'stat-card';
                card.innerHTML = `<div class="stat-label">${esc(c.label)}</div><div class="stat-value">${c.value}</div><div class="stat-sub">${esc(c.sub)}</div>`;
                grid.appendChild(card);
            });
            view.appendChild(grid);
        } catch (e) {
            view.appendChild(makeEmpty(e.message || '加载失败'));
        }
    }

    // ============ Tab: 用户管理 ============
    async function tabUsers(mount) {
        const view = makeView('用户管理');
        const toolbar = document.createElement('div');
        toolbar.className = 'admin-toolbar';
        toolbar.innerHTML = `
            <input type="text" id="u-q" placeholder="搜索用户名/邮箱" value="${esc(pageState.users.q)}">
            <select id="u-role">
                <option value="">全部角色</option>
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
            </select>
            <select id="u-status">
                <option value="">全部状态</option>
                <option value="active">正常</option>
                <option value="disabled">停用</option>
            </select>
            <button class="btn" id="u-search">查询</button>
            <span style="flex:1"></span>
            <span style="font-size:.74rem;color:var(--ink-faint)">停用/改密/降级会使该用户既有会话立即失效</span>
        `;
        view.appendChild(toolbar);
        const tableWrap = document.createElement('div');
        view.appendChild(tableWrap);
        mount.appendChild(view);

        // 回填过滤
        $('u-role').value = pageState.users.role;
        $('u-status').value = pageState.users.status;
        $('u-search').onclick = () => {
            pageState.users.q = $('u-q').value.trim();
            pageState.users.role = $('u-role').value;
            pageState.users.status = $('u-status').value;
            pageState.users.page = 1;
            loadUsers(tableWrap);
        };
        $('u-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('u-search').click(); });

        await loadUsers(tableWrap);
    }

    async function loadUsers(wrap) {
        const st = pageState.users;
        try {
            const data = await withLoading(wrap, API.listUsers({
                q: st.q, role: st.role, status: st.status,
                page: st.page, page_size: 20,
            }));
            const rows = data || [];
            if (!rows.length) { wrap.innerHTML = ''; wrap.appendChild(makeEmpty('无匹配用户')); return; }
            const tbl = document.createElement('table');
            tbl.className = 'data-table';
            tbl.innerHTML = `<thead><tr>
                <th>用户名</th><th>邮箱</th><th>角色</th><th>状态</th><th>注册时间</th><th>操作</th>
            </tr></thead><tbody></tbody>`;
            const tb = qs('tbody', tbl);
            rows.forEach(u => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td class="mono">${esc(u.username)}</td>
                    <td class="mono">${esc(u.email)}</td>
                    <td>${u.role === 'admin' ? badge('管理员', 'admin') : badge('普通')}</td>
                    <td>${u.is_active ? badge('正常') : badge('停用', 'disabled')}</td>
                    <td class="mono">${fmtDate(u.created_at)}</td>
                    <td><div class="row-actions"></div></td>`;
                const actions = qs('.row-actions', tr);
                actions.appendChild(actBtn('启用', () => userAction(u, 'enable'), u.is_active));
                actions.appendChild(actBtn('停用', () => userAction(u, 'disable'), !u.is_active, true));
                actions.appendChild(actBtn('重置密码', () => userReset(u)));
                actions.appendChild(actBtn('下线会话', () => userAction(u, 'revoke-sessions')));
                if (u.role === 'admin') {
                    actions.appendChild(actBtn('降级', () => userAction(u, 'demote'), false, true));
                } else {
                    actions.appendChild(actBtn('提升', () => userAction(u, 'promote')));
                }
                tb.appendChild(tr);
            });
            wrap.innerHTML = '';
            wrap.appendChild(tbl);
            wrap.appendChild(pager(data.total ?? 0, st.page, data.page_size || 20, (p) => { st.page = p; loadUsers(wrap); }));
        } catch (e) { /* withLoading 已渲染 */ }
    }

    async function userAction(u, op) {
        const labels = { enable: '启用', disable: '停用', 'revoke-sessions': '强制下线', promote: '提升为管理员', demote: '取消管理员' };
        if (!await confirmDialog(`确认对「${u.username}」执行「${labels[op]}」？`)) return;
        try {
            const fn = { enable: API.enableUser, disable: API.disableUser, 'revoke-sessions': API.revokeSessions, promote: API.promoteUser, demote: API.demoteUser }[op];
            await fn(u.id);
            API.toast(`已执行：${labels[op]}`, 'success');
            // 简单重载当前 tab
            switchTab(currentTab);
        } catch (e) { API.toast(e.message || '操作失败', 'error'); }
    }

    async function userReset(u) {
        const pwd = prompt(`为「${u.username}」设置新密码（留空则由系统生成临时口令）：`);
        if (pwd === null) return; // 取消
        try {
            const data = await API.resetUserPassword(u.id, pwd || null);
            if (data.generated) {
                prompt(`已重置「${u.username}」的密码，临时口令如下（请安全转交）：`, data.temp_password);
            } else {
                API.toast(`已重置「${u.username}」的密码`, 'success');
            }
            switchTab(currentTab);
        } catch (e) { API.toast(e.message || '重置失败', 'error'); }
    }

    // ============ Tab: 举报 ============
    async function tabReports(mount) {
        const view = makeView('内容举报');
        const toolbar = document.createElement('div');
        toolbar.className = 'admin-toolbar';
        toolbar.innerHTML = `
            <select id="r-status">
                <option value="pending">待处理</option>
                <option value="handled">已处理</option>
                <option value="dismissed">已驳回</option>
                <option value="all">全部</option>
            </select>
            <span style="font-size:.74rem;color:var(--ink-faint)">hide=隐藏目标 · delete=删除目标 · dismiss=驳回举报</span>
        `;
        view.appendChild(toolbar);
        const wrap = document.createElement('div');
        view.appendChild(wrap);
        mount.appendChild(view);
        $('r-status').value = pageState.reports.status;
        $('r-status').onchange = () => {
            pageState.reports.status = $('r-status').value;
            pageState.reports.page = 1;
            loadReports(wrap);
        };
        await loadReports(wrap);
    }

    async function loadReports(wrap) {
        const st = pageState.reports;
        try {
            const data = await withLoading(wrap, API.listReports({ status: st.status, page: st.page, page_size: 20 }));
            const rows = data || [];
            if (!rows.length) { wrap.innerHTML = ''; wrap.appendChild(makeEmpty('无举报记录')); return; }
            const tbl = document.createElement('table');
            tbl.className = 'data-table';
            tbl.innerHTML = `<thead><tr>
                <th>目标</th><th>类型</th><th>原因</th><th>状态</th><th>时间</th><th>操作</th>
            </tr></thead><tbody></tbody>`;
            const tb = qs('tbody', tbl);
            rows.forEach(r => {
                const tr = document.createElement('tr');
                const tgt = r.target || {};
                const tgtText = r.target_type === 'post' ? `帖子：${esc(tgt.title || '(已删除)')}` : `岗位：${esc(tgt.company || '(已删除)')}`;
                tr.innerHTML = `<td>${tgtText}</td>
                    <td>${badge(r.target_type)}</td>
                    <td>${esc(r.reason || '-')}</td>
                    <td>${badge(r.status, r.status)}</td>
                    <td class="mono">${fmtDate(r.created_at)}</td>
                    <td><div class="row-actions"></div></td>`;
                const actions = qs('.row-actions', tr);
                if (r.status === 'pending') {
                    actions.appendChild(actBtn('隐藏', () => handleReport(r, 'hide'), false, true));
                    actions.appendChild(actBtn('删除', () => handleReport(r, 'delete'), false, true));
                    actions.appendChild(actBtn('驳回', () => handleReport(r, 'dismiss')));
                }
                tb.appendChild(tr);
            });
            wrap.innerHTML = '';
            wrap.appendChild(tbl);
            wrap.appendChild(pager(data.total ?? 0, st.page, data.page_size || 20, (p) => { st.page = p; loadReports(wrap); }));
        } catch (e) {}
    }

    async function handleReport(r, action) {
        const labels = { hide: '隐藏目标', delete: '删除目标', dismiss: '驳回举报' };
        if (!await confirmDialog(`确认「${labels[action]}」此举报？`)) return;
        try {
            await API.handleReport(r.id, action, null);
            API.toast(`已处理：${labels[action]}`, 'success');
            switchTab(currentTab);
        } catch (e) { API.toast(e.message || '处理失败', 'error'); }
    }

    // ============ Tab: 帖子 ============
    async function tabPosts(mount) {
        const view = makeView('帖子管理');
        const toolbar = document.createElement('div');
        toolbar.className = 'admin-toolbar';
        toolbar.innerHTML = `
            <select id="p-status">
                <option value="">全部</option>
                <option value="normal">正常</option>
                <option value="pinned">置顶</option>
                <option value="hidden">隐藏</option>
                <option value="deleted">已删除</option>
            </select>`;
        view.appendChild(toolbar);
        const wrap = document.createElement('div');
        view.appendChild(wrap);
        mount.appendChild(view);
        $('p-status').value = pageState.posts.status;
        $('p-status').onchange = () => { pageState.posts.status = $('p-status').value; pageState.posts.page = 1; loadPosts(wrap); };
        await loadPosts(wrap);
    }

    async function loadPosts(wrap) {
        const st = pageState.posts;
        try {
            const data = await withLoading(wrap, API.listPosts({ status: st.status, page: st.page, page_size: 20 }));
            renderContentTable(wrap, data, st, [
                { key: 'title', label: '标题' },
                { key: 'category', label: '板块', render: v => badge(v) },
                { key: 'status', label: '状态', render: v => statusBadge(v) },
                { key: 'view_count', label: '浏览', mono: true },
                { key: 'comment_count', label: '评论', mono: true },
                { key: 'created_at', label: '时间', render: v => fmtDate(v), mono: true },
            ], (row, actions) => {
                actions.appendChild(actBtn('隐藏', () => postAction(row, 'hide'), row.status === 'hidden', true));
                actions.appendChild(actBtn('恢复', () => postAction(row, 'unhide'), row.status === 'normal'));
                actions.appendChild(actBtn('置顶', () => postAction(row, 'pin'), row.status === 'pinned' || row.status === 'hidden' || row.status === 'deleted'));
                actions.appendChild(actBtn('取消置顶', () => postAction(row, 'unpin'), row.status !== 'pinned'));
                actions.appendChild(actBtn('删除', () => postAction(row, 'delete'), row.status === 'deleted', true));
            });
        } catch (e) {}
    }

    async function postAction(row, op) {
        const labels = { hide: '隐藏', unhide: '恢复', pin: '置顶', unpin: '取消置顶', delete: '删除' };
        if (!await confirmDialog(`确认对帖子「${row.title}」执行「${labels[op]}」？`)) return;
        try {
            const fn = { hide: API.hidePost, unhide: API.unhidePost, pin: API.pinPost, unpin: API.unpinPost, delete: API.deletePost }[op];
            await fn(row.id);
            API.toast(`已执行：${labels[op]}`, 'success');
            switchTab(currentTab);
        } catch (e) { API.toast(e.message || '操作失败', 'error'); }
    }

    // ============ Tab: 岗位分享 ============
    async function tabJobShares(mount) {
        const view = makeView('岗位分享管理');
        const toolbar = document.createElement('div');
        toolbar.className = 'admin-toolbar';
        toolbar.innerHTML = `
            <select id="j-status">
                <option value="">全部</option>
                <option value="normal">正常</option>
                <option value="hidden">隐藏</option>
                <option value="deleted">已删除</option>
                <option value="expired">已过期</option>
            </select>`;
        view.appendChild(toolbar);
        const wrap = document.createElement('div');
        view.appendChild(wrap);
        mount.appendChild(view);
        $('j-status').value = pageState.jobshares.status;
        $('j-status').onchange = () => { pageState.jobshares.status = $('j-status').value; pageState.jobshares.page = 1; loadJobShares(wrap); };
        await loadJobShares(wrap);
    }

    async function loadJobShares(wrap) {
        const st = pageState.jobshares;
        try {
            const data = await withLoading(wrap, API.listJobShares({ status: st.status, page: st.page, page_size: 20 }));
            renderContentTable(wrap, data, st, [
                { key: 'company', label: '公司' },
                { key: 'position', label: '岗位' },
                { key: 'category', label: '行业', render: v => badge(v) },
                { key: 'status', label: '状态', render: v => statusBadge(v) },
                { key: 'click_count', label: '点击', mono: true },
                { key: 'created_at', label: '时间', render: v => fmtDate(v), mono: true },
            ], (row, actions) => {
                actions.appendChild(actBtn('隐藏', () => jobAction(row, 'hide'), row.status === 'hidden', true));
                actions.appendChild(actBtn('恢复', () => jobAction(row, 'unhide'), row.status === 'normal'));
                actions.appendChild(actBtn('删除', () => jobAction(row, 'delete'), row.status === 'deleted', true));
            });
        } catch (e) {}
    }

    async function jobAction(row, op) {
        const labels = { hide: '隐藏', unhide: '恢复', delete: '删除' };
        if (!await confirmDialog(`确认对「${row.company}」执行「${labels[op]}」？`)) return;
        try {
            const fn = { hide: API.hideJobShare, unhide: API.unhideJobShare, delete: API.deleteJobShare }[op];
            await fn(row.id);
            API.toast(`已执行：${labels[op]}`, 'success');
            switchTab(currentTab);
        } catch (e) { API.toast(e.message || '操作失败', 'error'); }
    }

    // ============ Tab: 审计日志 ============
    async function tabAudit(mount) {
        const view = makeView('审计日志');
        const toolbar = document.createElement('div');
        toolbar.className = 'admin-toolbar';
        toolbar.innerHTML = `
            <input type="text" id="a-action" placeholder="按 action 过滤，如 user.disable" value="${esc(pageState.audit.action)}">
            <button class="btn" id="a-search">查询</button>`;
        view.appendChild(toolbar);
        const wrap = document.createElement('div');
        view.appendChild(wrap);
        mount.appendChild(view);
        $('a-search').onclick = () => { pageState.audit.action = $('a-action').value.trim(); pageState.audit.page = 1; loadAudit(wrap); };
        $('a-action').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('a-search').click(); });
        await loadAudit(wrap);
    }

    async function loadAudit(wrap) {
        const st = pageState.audit;
        try {
            const data = await withLoading(wrap, API.listAudit({ action: st.action, page: st.page, page_size: 20 }));
            const rows = data || [];
            if (!rows.length) { wrap.innerHTML = ''; wrap.appendChild(makeEmpty('无审计记录')); return; }
            const tbl = document.createElement('table');
            tbl.className = 'data-table';
            tbl.innerHTML = `<thead><tr>
                <th>操作者</th><th>动作</th><th>目标</th><th>详情</th><th>时间</th>
            </tr></thead><tbody></tbody>`;
            const tb = qs('tbody', tbl);
            rows.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `<td>${esc(r.actor_username)}<br><span class="mono" style="font-size:.7rem;color:var(--ink-faint)">${esc(r.actor_id)}</span></td>
                    <td>${badge(r.action)}</td>
                    <td>${esc(r.target_type)} ${esc(r.target_id || '')}</td>
                    <td class="mono" style="font-size:.76rem;max-width:340px;word-break:break-all">${esc(r.detail || '-')}</td>
                    <td class="mono">${fmtDate(r.created_at)}</td>`;
                tb.appendChild(tr);
            });
            wrap.innerHTML = '';
            wrap.appendChild(tbl);
            wrap.appendChild(pager(data.total ?? 0, st.page, data.page_size || 20, (p) => { st.page = p; loadAudit(wrap); }));
        } catch (e) {}
    }

    // ============ Tab: 修改密码 ============
    function tabAccount(mount) {
        const view = makeView('修改我的密码');
        const card = document.createElement('div');
        card.className = 'admin-login-card';
        card.style.maxWidth = '420px';
        card.innerHTML = `
            <div class="login-sub">修改成功后会签发新令牌，旧令牌立即失效。</div>
            <div class="field"><label>原密码</label><input type="password" id="acc-old" autocomplete="current-password"></div>
            <div class="field"><label>新密码</label><input type="password" id="acc-new" autocomplete="new-password"></div>
            <div class="login-error" id="acc-error"></div>
            <button class="btn-primary" id="acc-save">保存</button>`;
        view.appendChild(card);
        mount.appendChild(view);
        $('acc-save').onclick = async () => {
            const oldp = $('acc-old').value, newp = $('acc-new').value;
            const errEl = $('acc-error'); errEl.textContent = '';
            if (!oldp || !newp) { errEl.textContent = '请填写原密码与新密码'; return; }
            try {
                const data = await API.changePassword(oldp, newp);
                API.setToken(data.token);
                API.toast('密码已修改，登录状态已刷新', 'success');
                $('acc-old').value = ''; $('acc-new').value = '';
            } catch (e) { errEl.textContent = e.message || '修改失败'; }
        };
    }

    // ============ 共享渲染工具 ============
    function makeView(title) {
        const v = document.createElement('div');
        v.className = 'admin-view';
        v.innerHTML = `<h1 class="admin-view-title">${esc(title)}</h1>`;
        return v;
    }

    function makeEmpty(text) {
        const d = document.createElement('div');
        d.className = 'empty-state'; d.textContent = text;
        return d;
    }

    function actBtn(label, onclick, disabled, danger) {
        const b = document.createElement('button');
        b.className = 'btn-act' + (danger ? ' danger' : '');
        b.textContent = label; b.disabled = !!disabled;
        if (!disabled) b.onclick = onclick;
        return b;
    }

    function renderContentTable(wrap, data, st, columns, renderActions) {
        const rows = data || [];
        if (!rows.length) { wrap.innerHTML = ''; wrap.appendChild(makeEmpty('无数据')); return; }
        const tbl = document.createElement('table');
        tbl.className = 'data-table';
        const thead = '<tr>' + columns.map(c => `<th>${esc(c.label)}</th>`).join('') + '<th>操作</th></tr>';
        tbl.innerHTML = `<thead>${thead}</thead><tbody></tbody>`;
        const tb = qs('tbody', tbl);
        rows.forEach(row => {
            const tr = document.createElement('tr');
            let html = '';
            columns.forEach(c => {
                const v = row[c.key];
                const cell = c.render ? c.render(v) : esc(v);
                html += `<td${c.mono ? ' class="mono"' : ''}>${cell}</td>`;
            });
            html += '<td><div class="row-actions"></div></td>';
            tr.innerHTML = html;
            renderActions(row, qs('.row-actions', tr));
            tb.appendChild(tr);
        });
        wrap.innerHTML = '';
        wrap.appendChild(tbl);
        wrap.appendChild(pager(data.total ?? 0, st.page, data.page_size || 20, (p) => { st.page = p; switchTab(currentTab); }));
    }

    // ============ Tab 注册表 ============
    const TABS = {
        dashboard: tabDashboard,
        users: tabUsers,
        reports: tabReports,
        posts: tabPosts,
        jobshares: tabJobShares,
        audit: tabAudit,
        account: tabAccount,
    };

    // ============ 入口 ============
    function init() {
        bindLogin();
        bindLogout();
        bindNav();
        bootstrap();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
