/**
 * OfferClaw 主控制器
 * 注册所有视图、初始化路由、绑定导航、健康检查
 *
 * 内测模式：单用户，无登录守卫，直接进入对话页
 */
(function (global) {
    'use strict';

    const Router = global.OfferClawRouter;
    const API = global.OfferClawAPI;
    const Views = global.OfferClawViews || {};

    /**
     * 注册所有视图
     */
    function registerViews() {
        if (Views.chat)     Router.register('/chat', Views.chat);
        if (Views.kanban)   Router.register('/kanban', Views.kanban);
        if (Views.profile)  Router.register('/profile', Views.profile);
        if (Views.jobs)     Router.register('/jobs', Views.jobs);
        // 智能填表正在升级为浏览器插件，屏蔽原功能，访问该路由显示升级提示
        Router.register('/smart-fill', {
            title: '智能填表（升级中）',
            mount: function (el) {
                el.innerHTML =
                    '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:50vh;gap:1rem;text-align:center;padding:2rem;">' +
                    '<h2 style="margin:0">智能填表正在升级为浏览器插件</h2>' +
                    '<p style="margin:0;max-width:32rem;opacity:0.75">为了更精准地识别表单字段、复用你在浏览器中的登录状态，并避免后端代理抓取带来的跨域与反爬限制，该功能正在改造为浏览器插件形式。完成后请安装插件继续使用。</p>' +
                    '</div>';
            },
            cleanup: function () {}
        });
        if (Views.interview) Router.register('/interview', Views.interview);
        if (Views.settings) Router.register('/settings', Views.settings);
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

        // 返回对话按钮
        const backBtn = document.getElementById('btn-back-chat');
        if (backBtn) {
            backBtn.addEventListener('click', () => Router.navigate('/chat'));
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
            // 授权门控：未激活且非开发模式 → 跳激活页（生产部署首屏即拦截）
            const svc = data && data.services;
            if (svc && svc.license_activated === false && !svc.license_dev_mode) {
                if (!/\/license\.html(\?.*)?$/.test(location.pathname)) {
                    location.href = 'license.html';
                    return;
                }
            }
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
        registerViews();
        bindNavigation();
        Router.init();
        startHealthCheck();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    global.OfferClawApp = { init, checkHealth };
})(window);
