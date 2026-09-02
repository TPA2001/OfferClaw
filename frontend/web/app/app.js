/**
 * OfferCabin 主控制器
 * 注册所有视图、初始化路由、绑定导航、健康检查、登录守卫
 */
(function (global) {
    'use strict';

    const Router = global.OfferCabinRouter;
    const API = global.OfferCabinAPI;
    const Views = global.OfferCabinViews || {};

    /**
     * 注册所有视图
     */
    function registerViews() {
        if (Views.chat)      Router.register('/chat', Views.chat);
        if (Views.overview)  Router.register('/overview', Views.overview);
        if (Views.kanban)   Router.register('/kanban', Views.kanban);
        if (Views.profile)  Router.register('/profile', Views.profile);
        if (Views.interview) Router.register('/interview', Views.interview);
        if (Views.community) Router.register('/community', Views.community);
        if (Views.jobShares) Router.register('/job-shares', Views.jobShares);
        if (Views.settings) Router.register('/settings', Views.settings);
        // 未注册路由回落到投递总览
    }

    /**
     * 绑定导航点击
     */
    function bindNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const route = item.dataset.route;
                if (route) Router.navigate(route);
            });
        });

        // 退出登录
        const logoutBtn = document.getElementById('btn-logout');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                API.auth.logout();
            });
        }
    }

    /**
     * 顶部显示当前用户 + 刷新用户信息
     */
    // 取用户名前 1-2 个字符作为头像缩写
    function initials(name) {
        if (!name) return 'OC';
        return name.trim().slice(0, 2).toUpperCase();
    }

    async function loadUserInfo() {
        const user = API.currentUser();
        const el = document.getElementById('current-user');
        const av = document.getElementById('user-avatar');
        const apply = (name) => {
            if (el) el.textContent = name || '';
            if (av) av.textContent = initials(name);
        };
        apply(user ? user.username : '');
        try {
            const fresh = await API.auth.me();
            apply(fresh.username);
            // 管理员入口：仅管理员可见，指向独立端口的管理后台
            if (fresh.is_admin) {
                const navAdmin = document.getElementById('nav-admin');
                if (navAdmin) {
                    const cfg = global.OFFERCABIN_CONFIG || {};
                    const port = cfg.ADMIN_PORT || 8001;
                    const host = (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
                        ? `${location.hostname}:${port}`
                        : location.host.replace(/:\d+$/, '') + ':' + port;
                    navAdmin.href = `${location.protocol}//${host}/`;
                    navAdmin.style.display = '';
                }
            }
        } catch (e) {
            // 401 已在 api.js 中处理跳转；其余静默
        }
    }

    /**
     * 健康检查（轮询）
     */
    let healthTimer = null;
    async function checkHealth() {
        const el = document.getElementById('health-indicator');
        if (!el) return;
        const dot = el.querySelector('.health-dot');
        const text = el.querySelector('.health-text');
        try {
            const data = await API.health();
            const ok = data && (data.status === 'ok' || data.status === 'healthy');
            dot.classList.toggle('down', !ok);
            text.textContent = ok ? '已连接' : '异常';
        } catch (e) {
            dot.classList.add('down');
            text.textContent = '离线';
        }
    }

    function startHealthCheck() {
        checkHealth();
        healthTimer = setInterval(checkHealth, 30000);
    }

    /**
     * 初始化
     */
    function init() {
        // 登录守卫：未登录一律回登录页
        if (!API.isLoggedIn()) {
            location.href = 'login.html';
            return;
        }
        registerViews();
        bindNavigation();
        loadUserInfo();
        Router.init();
        startHealthCheck();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    global.OfferCabinApp = { init, checkHealth };
})(window);
