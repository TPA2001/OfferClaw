/**
 * OfferClaw Motion System
 *
 * 轻量级动画工具库，提供滚动入场、数字滚动、条形图填充、
 * 错开入场与 tab 切换过渡等能力。所有方法均挂在 window.OfferClawMotion。
 *
 * 设计原则：
 * - 优先使用 CSS 过渡/关键帧，JS 只负责触发时机
 * - 尊重 prefers-reduced-motion，开启时跳过动画直接到终态
 * - 安全兜底：元素缺失时不抛错，静默返回
 */
(function () {
    'use strict';

    var REDUCED = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function prefersReducedMotion() {
        return REDUCED ||
            (window.matchMedia &&
                window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    // ============ Count Up ============
    /**
     * 数字从 0 滚动到目标值
     * @param {HTMLElement} el     承载数字的元素
     * @param {number} target      目标值
     * @param {object} opts        { duration, decimals, suffix, prefix }
     */
    function countUp(el, target, opts) {
        if (!el) return;
        opts = opts || {};
        var duration = opts.duration || 900;
        var decimals = opts.decimals || 0;
        var suffix = opts.suffix || '';
        var prefix = opts.prefix || '';
        var targetNum = Number(target) || 0;

        // 降级：减少动效时直接显示终值
        if (prefersReducedMotion()) {
            el.textContent = prefix + targetNum.toFixed(decimals) + suffix;
            return;
        }

        var start = null;
        var startVal = 0;
        el.classList.add('counting');

        function frame(ts) {
            if (!start) start = ts;
            var progress = Math.min((ts - start) / duration, 1);
            // easeOutCubic
            var eased = 1 - Math.pow(1 - progress, 3);
            var current = startVal + (targetNum - startVal) * eased;
            el.textContent = prefix + current.toFixed(decimals) + suffix;
            if (progress < 1) {
                requestAnimationFrame(frame);
            } else {
                el.textContent = prefix + targetNum.toFixed(decimals) + suffix;
                el.classList.remove('counting');
            }
        }
        requestAnimationFrame(frame);
    }

    /**
     * 批量 countUp：扫描选择器内带 data-target 的元素
     * @param {string} selector  默认 '.count-up'
     */
    function countUpAll(selector) {
        var nodes = document.querySelectorAll(selector || '.count-up');
        nodes.forEach(function (el) {
            var target = parseFloat(el.dataset.target || el.dataset.count || '0');
            var decimals = parseInt(el.dataset.decimals || '0', 10);
            var suffix = el.dataset.suffix || '';
            countUp(el, target, { duration: 1000, decimals: decimals, suffix: suffix });
        });
    }

    // ============ Fill Bars ============
    /**
     * 触发容器内条形图从 0 填充到 data-target-width
     * 依赖 .bar-fill-animate 的 CSS 过渡：加 .filled 后 width 变为 --target-width
     * @param {HTMLElement} container
     */
    function fillBars(container) {
        if (!container) return;
        var bars = container.querySelectorAll('.bar-fill-animate[data-target-width]');
        bars.forEach(function (bar) {
            var target = bar.getAttribute('data-target-width') || '0%';
            // 先重置确保动画可重复触发
            bar.classList.remove('filled');
            bar.style.setProperty('--target-width', target);
            // 强制重排后再加上 filled，让过渡生效
            void bar.offsetWidth;
            // 尊重 --fill-delay（CSS 中已定义 transition-delay）
            bar.classList.add('filled');
        });
    }

    // ============ Reveal on Scroll ============
    /**
     * 用 IntersectionObserver 为 .reveal/.reveal-x/.reveal-scale 元素
     * 在进入视口时添加 .in 类触发 CSS 过渡。
     */
    function revealOnScroll() {
        var revealEls = document.querySelectorAll('.reveal, .reveal-x, .reveal-scale');
        if (revealEls.length === 0) return;

        // 降级：不支持 IntersectionObserver 或减少动效，直接全部显示
        if (!('IntersectionObserver' in window) || prefersReducedMotion()) {
            revealAll();
            return;
        }

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('in');
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.12,
            rootMargin: '0px 0px -40px 0px'
        });

        revealEls.forEach(function (el) { observer.observe(el); });
    }

    /**
     * 立即为所有 reveal 元素添加 .in（无需滚动触发）
     */
    function revealAll() {
        document.querySelectorAll('.reveal, .reveal-x, .reveal-scale').forEach(function (el) {
            el.classList.add('in');
        });
    }

    // ============ Stagger In ============
    /**
     * 为容器内子元素应用错开入场动画
     * @param {HTMLElement} container
     * @param {string} childSelector  子元素选择器，默认所有直接子元素
     * @param {object} opts           { step, duration, keyframe }
     */
    function staggerIn(container, childSelector, opts) {
        if (!container) return;
        opts = opts || {};
        var step = opts.step || 50;
        var duration = opts.duration || '0.45s';
        var keyframe = opts.keyframe || 'staggerIn';
        var easing = 'var(--ease-out)';

        var children = childSelector
            ? container.querySelectorAll(childSelector)
            : container.children;

        if (prefersReducedMotion()) return;

        children.forEach(function (child, i) {
            child.style.animation = 'none';
            void child.offsetWidth;
            child.style.animation = keyframe + ' ' + duration + ' ' + easing + ' backwards';
            child.style.animationDelay = (i * step) + 'ms';
        });
    }

    // ============ Tab Enter ============
    /**
     * Tab 面板切换时添加方向性入场动画
     * @param {HTMLElement} panel
     */
    function tabEnter(panel) {
        if (!panel) return;
        if (prefersReducedMotion()) return;
        panel.classList.remove('tab-panel-enter');
        void panel.offsetWidth;
        panel.classList.add('tab-panel-enter');
    }

    // ============ 自动初始化 ============
    // DOM 就绪后自动触发滚动入场（各页面也可手动再次调用 revealAll）
    function autoInit() {
        revealOnScroll();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }

    // ============ 导出 ============
    window.OfferClawMotion = {
        revealOnScroll: revealOnScroll,
        revealAll: revealAll,
        countUp: countUp,
        countUpAll: countUpAll,
        fillBars: fillBars,
        staggerIn: staggerIn,
        tabEnter: tabEnter,
        prefersReducedMotion: prefersReducedMotion
    };
})();
