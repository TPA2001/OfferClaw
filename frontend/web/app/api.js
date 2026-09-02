/**
 * OfferCabin 统一 API 客户端
 * 封装 REST 调用、SSE 流式读取、统一响应信封处理、JWT 鉴权
 *
 * 鉴权：Token 存 localStorage('oc_token')，所有请求自动带 Authorization: Bearer
 * 401 业务码（40100/40101/40103 等）自动跳转登录页（login.html 上不跳）
 */
(function (global) {
    'use strict';

    const CONFIG = global.OFFERCABIN_CONFIG || {
        API_BASE: (global.OFFERCABIN_API_BASE || ''),
    };
    const TOKEN_KEY = 'oc_token';
    const USER_KEY = 'oc_user';

    const API_V1 = CONFIG.API_BASE + '/api/v1';

    /**
     * 读取当前登录 Token
     */
    function token() {
        try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
    }

    function setToken(t) {
        try {
            if (t) localStorage.setItem(TOKEN_KEY, t);
            else localStorage.removeItem(TOKEN_KEY);
        } catch (e) {}
    }

    function currentUser() {
        try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch (e) { return null; }
    }

    function setCurrentUser(u) {
        try {
            if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
            else localStorage.removeItem(USER_KEY);
        } catch (e) {}
    }

    function isLoggedIn() {
        return !!token();
    }

    /**
     * 统一 headers（含鉴权）
     */
    function headers(extra) {
        const h = { 'Authorization': 'Bearer ' + token() };
        if (extra) Object.assign(h, extra);
        return h;
    }

    /**
     * JSON headers
     */
    function jsonHeaders() {
        return headers({ 'Content-Type': 'application/json' });
    }

    /**
     * 检查响应信封 {code, message, data}
     * code === 0 表示成功，否则抛错
     */
    function checkEnvelope(res) {
        if (res.code === 0) return res.data;
        const err = new Error(res.message || '请求失败');
        err.code = res.code;
        err.detail = res.detail;
        throw err;
    }

    /**
     * 鉴权拦截：401 业务码 → 清除登录态并跳转登录页（登录页自身不跳）
     * - 40100 未登录/令牌无效 / 40101 过期 / 40103 密码已变更 → 跳登录
     * - 40102 账号停用 → 不清 token，交由页面提示
     */
    function authRedirect(status, errBody) {
        if (status !== 401 || !errBody) return;
        const code = errBody.code;
        if (code === 40100 || code === 40101 || code === 40103) {
            if (!/\/login\.html(\?.*)?$/.test(location.pathname)) {
                setToken('');
                setCurrentUser(null);
                location.href = 'login.html' + (code === 40101 ? '?reason=expired' : '');
            }
        }
    }

    /**
     * REST GET
     */
    async function get(path, { timeout = 30000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'GET',
                headers: headers(),
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                authRedirect(resp.status, body);
                throw Object.assign(new Error(body.message || `HTTP ${resp.status}`), { code: body.code, status: resp.status });
            }
            return checkEnvelope(await resp.json());
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * REST POST
     */
    async function post(path, body, { timeout = 60000, raw = false } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'POST',
                headers: jsonHeaders(),
                body: JSON.stringify(body || {}),
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                authRedirect(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            const json = await resp.json();
            return raw ? json : checkEnvelope(json);
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * multipart/form-data 上传（如 PDF 导入），自动带鉴权头
     */
    async function postForm(path, formData, { timeout = 120000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'POST',
                headers: headers(), // 不手动设 Content-Type，让浏览器自动带 multipart boundary
                body: formData,
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                authRedirect(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            return checkEnvelope(await resp.json());
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * REST PUT
     */
    async function put(path, body, { timeout = 60000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'PUT',
                headers: jsonHeaders(),
                body: JSON.stringify(body || {}),
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                authRedirect(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            return checkEnvelope(await resp.json());
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * REST PATCH
     */
    async function patch(path, body, { timeout = 30000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'PATCH',
                headers: jsonHeaders(),
                body: JSON.stringify(body || {}),
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                authRedirect(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            return checkEnvelope(await resp.json());
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * REST DELETE
     */
    async function del(path, { timeout = 30000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'DELETE',
                headers: headers(),
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                authRedirect(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            return checkEnvelope(await resp.json());
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * SSE 流式请求（POST）
     * @param {string} path - API 路径（不含 /api/v1 前缀）
     * @param {object} body - 请求体
     * @param {function} onEvent - 事件回调 (event) => void
     * @param {object} opts - { timeout }
     * @returns {Promise<void>}
     */
    async function stream(path, body, onEvent, { timeout = 300000 } = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeout);
        try {
            const resp = await fetch(API_V1 + path, {
                method: 'POST',
                headers: jsonHeaders(),
                body: JSON.stringify(body || {}),
                signal: ctrl.signal,
            });
            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({}));
                authRedirect(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const payload = line.slice(6).trim();
                    if (!payload) continue;
                    try {
                        const evt = JSON.parse(payload);
                        onEvent(evt);
                    } catch (e) {
                        console.warn('SSE 事件解析失败:', payload, e);
                    }
                }
            }
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * 健康检查（无鉴权）
     */
    async function health() {
        const resp = await fetch(CONFIG.API_BASE + '/health', { method: 'GET' });
        return resp.json();
    }

    /**
     * HTML 转义
     */
    function esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * 简单 toast
     */
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
        setTimeout(() => {
            el.classList.remove('show');
            setTimeout(() => el.remove(), 300);
        }, duration);
    }

    // ============ 账号 API ============
    async function authLogin(account, password) {
        const data = await post('/auth/login', { account, password });
        setToken(data.token);
        setCurrentUser(data.user);
        return data.user;
    }
    async function authRegister(payload) {
        const data = await post('/auth/register', payload);
        setToken(data.token);
        setCurrentUser(data.user);
        return data.user;
    }
    async function authMe() {
        const user = await get('/auth/me');
        setCurrentUser(user);
        return user;
    }
    async function authChangePassword(old_password, new_password) {
        const data = await post('/auth/change-password', { old_password, new_password });
        setToken(data.token); // 改密后签发新 token，旧 token 失效
        return data.user;
    }
    async function authForgotPassword(email) {
        return post('/auth/forgot-password', { email });
    }
    async function authResetPassword(token, new_password) {
        const data = await post('/auth/reset-password', { token, new_password });
        setToken(data.token);
        setCurrentUser(data.user);
        return data.user;
    }
    function authLogout() {
        setToken('');
        setCurrentUser(null);
        location.href = 'login.html';
    }

    // ============ 社区 / 岗位分享 ============

    async function communityListPosts(params) {
        const qs = new URLSearchParams(params || {}).toString();
        return get('/community/posts' + (qs ? '?' + qs : ''));
    }
    async function communityGetPost(id) { return get('/community/posts/' + encodeURIComponent(id)); }
    async function communityCreatePost(body) { return post('/community/posts', body); }
    async function communityUpdatePost(id, body) { return put('/community/posts/' + encodeURIComponent(id), body); }
    async function communityDeletePost(id) { return del('/community/posts/' + encodeURIComponent(id)); }
    async function communityListComments(id, limit) {
        return get('/community/posts/' + encodeURIComponent(id) + '/comments?limit=' + (limit || 200));
    }
    async function communityCreateComment(id, body) {
        return post('/community/posts/' + encodeURIComponent(id) + '/comments', body);
    }
    async function communityDeleteComment(id) { return del('/community/comments/' + encodeURIComponent(id)); }

    async function communityListJobs(params) {
        const qs = new URLSearchParams(params || {}).toString();
        return get('/community/job-shares' + (qs ? '?' + qs : ''));
    }
    async function communityGetJob(id) { return get('/community/job-shares/' + encodeURIComponent(id)); }
    async function communityCreateJob(body) { return post('/community/job-shares', body); }
    async function communityUpdateJob(id, body) { return put('/community/job-shares/' + encodeURIComponent(id), body); }
    async function communityDeleteJob(id) { return del('/community/job-shares/' + encodeURIComponent(id)); }
    async function communityRedirectJob(id) {
        return get('/community/job-shares/' + encodeURIComponent(id) + '/redirect');
    }
    async function communityJobToApplication(id) {
        return post('/community/job-shares/' + encodeURIComponent(id) + '/to-application');
    }
    async function communityExpireJob(id) {
        return post('/community/job-shares/' + encodeURIComponent(id) + '/expire');
    }

    async function communityReact(body) { return post('/community/reactions', body); }
    async function communityReport(body) { return post('/community/reports', body); }

    global.OfferCabinAPI = {
        CONFIG,
        API_V1,
        token,
        setToken,
        currentUser,
        setCurrentUser,
        isLoggedIn,
        headers,
        jsonHeaders,
        get,
        post,
        postForm,
        put,
        patch,
        del,
        stream,
        health,
        esc,
        toast,
        auth: {
            login: authLogin,
            register: authRegister,
            me: authMe,
            changePassword: authChangePassword,
            forgotPassword: authForgotPassword,
            resetPassword: authResetPassword,
            logout: authLogout,
        },
        community: {
            listPosts: communityListPosts,
            getPost: communityGetPost,
            createPost: communityCreatePost,
            updatePost: communityUpdatePost,
            deletePost: communityDeletePost,
            listComments: communityListComments,
            createComment: communityCreateComment,
            deleteComment: communityDeleteComment,
            listJobs: communityListJobs,
            getJob: communityGetJob,
            createJob: communityCreateJob,
            updateJob: communityUpdateJob,
            deleteJob: communityDeleteJob,
            redirectJob: communityRedirectJob,
            jobToApplication: communityJobToApplication,
            expireJob: communityExpireJob,
            react: communityReact,
            report: communityReport,
        },
    };
})(window);
