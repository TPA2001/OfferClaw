/**
 * OfferClaw SPA 路由器
 * 基于 hash 的轻量路由：#/chat, #/kanban, #/profile, #/jobs, #/smart-fill, #/interview, #/settings
 */
(function (global) {
    'use strict';

    const routes = {};
    let currentView = null;
    let currentCleanup = null;
    const mountEl = () => document.getElementById('view-mount');

    /**
     * 注册路由
     * @param {string} path - 路径如 '/chat'
     * @param {object} view - { mount(container, params) => cleanup|null, title }
     */
    function register(path, view) {
        routes[path] = view;
    }

    /**
     * 解析当前 hash
     */
    function parseHash() {
        const hash = global.location.hash.slice(1) || '/overview';
        const [path, queryStr] = hash.split('?');
        const params = {};
        if (queryStr) {
            queryStr.split('&').forEach(kv => {
                const [k, v] = kv.split('=');
                params[decodeURIComponent(k)] = decodeURIComponent(v || '');
            });
        }
        return { path: path || '/overview', params };
    }

    /**
     * 导航到指定路由
     */
    function navigate(path, params) {
        let hash = '#' + path;
        if (params && Object.keys(params).length) {
            const qs = Object.entries(params)
                .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
                .join('&');
            hash += '?' + qs;
        }
        if (global.location.hash === hash) {
            // 相同路由，手动触发
            render();
        } else {
            global.location.hash = hash;
        }
    }

    /**
     * 渲染当前路由
     */
    async function render() {
        const { path, params } = parseHash();
        const view = routes[path] || routes['/overview'];
        const el = mountEl();
        if (!el) return;

        // 清理上一个视图
        if (currentCleanup) {
            try { currentCleanup(); } catch (e) { console.warn('View cleanup failed:', e); }
            currentCleanup = null;
        }

        // 淡出过渡
        el.classList.add('view-switching');
        await new Promise(r => setTimeout(r, 50));

        el.innerHTML = '';
        el.scrollTop = 0;

        try {
            currentView = path;
            const cleanup = await view.mount(el, params);
            currentCleanup = cleanup || null;

            // 更新导航激活态
            document.querySelectorAll('.nav-item').forEach(item => {
                item.classList.toggle('active', item.dataset.route === path);
            });

            // 淡入
            requestAnimationFrame(() => {
                el.classList.remove('view-switching');
            });
        } catch (e) {
            console.error('View mount failed:', e);
            el.innerHTML = '<div class="view-error"><p>视图加载失败</p><pre>' + (e.message || e) + '</pre></div>';
            el.classList.remove('view-switching');
        }
    }

    /**
     * 初始化路由
     */
    function init() {
        if (!global.location.hash) {
            global.location.hash = '#/overview';
        }
        global.addEventListener('hashchange', render);
        render();
    }

    global.OfferClawRouter = { register, navigate, parseHash, init };
})(window);
