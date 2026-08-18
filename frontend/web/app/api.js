/**
 * OfferClaw 统一 API 客户端
 * 封装 REST 调用、SSE 流式读取、统一响应信封处理
 */
(function (global) {
    'use strict';

    const CONFIG = global.OFFERCLAW_CONFIG || {
        API_BASE: (global.OFFERCLAW_API_BASE || 'http://localhost:8000'),
        TOKEN: (global.OFFERCLAW_TOKEN || 'demo-token'),
    };

    const API_V1 = CONFIG.API_BASE + '/api/v1';

    /**
     * 统一 headers（含鉴权）
     */
    function headers(extra) {
        const h = { 'Authorization': 'Bearer ' + CONFIG.TOKEN };
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
     * 授权门控拦截：403 + license 业务码 → 跳激活页
     * - 40301 未激活 / 40302 已过期 → 跳转 license.html
     * - 40303 功能未授权 → 不跳转，交由调用方提示升级
     */
    function gateCheck(status, errBody) {
        if (status !== 403 || !errBody) return;
        const code = errBody.code;
        if (code === 40301 || code === 40302) {
            if (!/\/license\.html(\?.*)?$/.test(location.pathname)) {
                location.href = 'license.html' + (code === 40302 ? '?reason=expired' : '');
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
                gateCheck(resp.status, body);
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
                gateCheck(resp.status, errBody);
                throw Object.assign(new Error(errBody.message || `HTTP ${resp.status}`), { code: errBody.code, status: resp.status });
            }
            const json = await resp.json();
            return raw ? json : checkEnvelope(json);
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
                gateCheck(resp.status, errBody);
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
                gateCheck(resp.status, errBody);
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
                gateCheck(resp.status, errBody);
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
                gateCheck(resp.status, errBody);
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
                buffer = lines.pop(); // 保留最后不完整的行
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

    // ============ 授权激活 API ============
    // 直接走 /api/v1/license/*（不走门控，本身即公开接口）
    async function licenseStatus() {
        const resp = await fetch(API_V1 + '/license/status', { headers: headers() });
        const json = await resp.json();
        return json.data;
    }
    async function licenseActivate(key) {
        const resp = await fetch(API_V1 + '/license/activate', {
            method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ key }),
        });
        const json = await resp.json();
        if (!resp.ok) {
            const e = new Error(json.message || '激活失败');
            e.code = json.code; e.detail = json.detail; throw e;
        }
        return json.data;
    }
    async function licenseDeactivate() {
        const resp = await fetch(API_V1 + '/license/deactivate', {
            method: 'POST', headers: jsonHeaders(), body: '{}',
        });
        const json = await resp.json();
        return json.data;
    }
    async function licenseMachine() {
        const resp = await fetch(API_V1 + '/license/machine', { headers: headers() });
        const json = await resp.json();
        return json.data;
    }

    global.OfferClawAPI = {
        CONFIG,
        API_V1,
        headers,
        jsonHeaders,
        get,
        post,
        put,
        patch,
        del,
        stream,
        health,
        esc,
        toast,
        license: {
            status: licenseStatus,
            activate: licenseActivate,
            deactivate: licenseDeactivate,
            machine: licenseMachine,
        },
    };
})(window);
