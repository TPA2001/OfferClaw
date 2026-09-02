/**
 * OfferCabin 管理后台 API 客户端
 *
 * 与主站隔离：令牌存 localStorage('oc_admin_token')，401 回登录卡。
 * 管理前端与 API 同源（均由管理端口提供），故 API_BASE 为空（相对路径）。
 */
(function (global) {
    'use strict';

    const TOKEN_KEY = 'oc_admin_token';
    const API_V1 = '/api/v1/admin';

    function token() {
        try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
    }
    function setToken(t) {
        try {
            if (t) localStorage.setItem(TOKEN_KEY, t);
            else localStorage.removeItem(TOKEN_KEY);
        } catch (e) {}
    }
    function isLoggedIn() { return !!token(); }

    function headers(extra) {
        const h = { 'Authorization': 'Bearer ' + token() };
        if (extra) Object.assign(h, extra);
        return h;
    }
    function jsonHeaders() { return headers({ 'Content-Type': 'application/json' }); }

    function checkEnvelope(res) {
        if (res.code !== 0) {
            const err = new Error(res.message || '请求失败');
            err.code = res.code; err.detail = res.detail;
            throw err;
        }
        const data = res.data;
        // 列表响应：ok() 的 extra（total/page/page_size）在顶层，挂到数组上供分页使用
        if (Array.isArray(data)) {
            ['total', 'page', 'page_size'].forEach(function (k) {
                if (res[k] !== undefined) data[k] = res[k];
            });
        }
        return data;
    }

    // 401 业务码 → 清除令牌，触发回登录（由 app.js 监听 onAuthFail）
    function handleAuthFail(status, body) {
        if (status === 401 && body && [40100, 40101, 40102, 40103].includes(body.code)) {
            setToken('');
            if (typeof global.onAdminAuthFail === 'function') global.onAdminAuthFail(body.code);
        }
    }

    async function request(method, path, body, { timeout = 30000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const opts = { method, headers: method === 'GET' || method === 'DELETE' ? headers() : jsonHeaders(), signal: ctrl.signal };
            if (body !== undefined && method !== 'GET' && method !== 'DELETE') opts.body = JSON.stringify(body || {});
            const resp = await fetch(API_V1 + path, opts);
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                handleAuthFail(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            return checkEnvelope(await resp.json());
        } finally {
            clearTimeout(timer);
        }
    }

    function esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function toast(message, type = 'info', duration = 3000) {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const el = document.createElement('div');
        el.className = 'toast ' + type;
        el.textContent = message;
        container.appendChild(el);
        requestAnimationFrame(() => el.classList.add('show'));
        setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, duration);
    }

    // ============ 管理端 API ============
    const AdminAPI = {
        token, setToken, isLoggedIn, esc, toast, API_V1,
        login(account, password) {
            return request('POST', '/login', { account, password }, { timeout: 15000 });
        },
        me() { return request('GET', '/me'); },
        changePassword(old_password, new_password) {
            return request('POST', '/change-password', { old_password, new_password });
        },
        stats() { return request('GET', '/stats'); },

        listUsers(params) {
            const qs = new URLSearchParams(params || {}).toString();
            return request('GET', '/users' + (qs ? '?' + qs : ''));
        },
        disableUser(id) { return request('POST', '/users/' + encodeURIComponent(id) + '/disable'); },
        enableUser(id) { return request('POST', '/users/' + encodeURIComponent(id) + '/enable'); },
        resetUserPassword(id, new_password) {
            return request('POST', '/users/' + encodeURIComponent(id) + '/reset-password', { new_password: new_password || null });
        },
        promoteUser(id) { return request('POST', '/users/' + encodeURIComponent(id) + '/promote'); },
        demoteUser(id) { return request('POST', '/users/' + encodeURIComponent(id) + '/demote'); },
        revokeSessions(id) { return request('POST', '/users/' + encodeURIComponent(id) + '/revoke-sessions'); },

        listReports(params) {
            const qs = new URLSearchParams(params || {}).toString();
            return request('GET', '/reports' + (qs ? '?' + qs : ''));
        },
        handleReport(id, action, note) {
            return request('POST', '/reports/' + encodeURIComponent(id) + '/handle', { action, note });
        },

        listPosts(params) {
            const qs = new URLSearchParams(params || {}).toString();
            return request('GET', '/posts' + (qs ? '?' + qs : ''));
        },
        hidePost(id) { return request('POST', '/posts/' + encodeURIComponent(id) + '/hide'); },
        unhidePost(id) { return request('POST', '/posts/' + encodeURIComponent(id) + '/unhide'); },
        pinPost(id) { return request('POST', '/posts/' + encodeURIComponent(id) + '/pin'); },
        unpinPost(id) { return request('POST', '/posts/' + encodeURIComponent(id) + '/unpin'); },
        deletePost(id) { return request('DELETE', '/posts/' + encodeURIComponent(id)); },

        listJobShares(params) {
            const qs = new URLSearchParams(params || {}).toString();
            return request('GET', '/job-shares' + (qs ? '?' + qs : ''));
        },
        hideJobShare(id) { return request('POST', '/job-shares/' + encodeURIComponent(id) + '/hide'); },
        unhideJobShare(id) { return request('POST', '/job-shares/' + encodeURIComponent(id) + '/unhide'); },
        deleteJobShare(id) { return request('DELETE', '/job-shares/' + encodeURIComponent(id)); },

        deleteComment(id) { return request('DELETE', '/comments/' + encodeURIComponent(id)); },

        listAudit(params) {
            const qs = new URLSearchParams(params || {}).toString();
            return request('GET', '/audit-log' + (qs ? '?' + qs : ''));
        },
    };

    global.AdminAPI = AdminAPI;
})(window);
