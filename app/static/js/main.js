/**
 * NewsRadar Pro v2.0 — 全局交互
 */
(function() {
    'use strict';

    // ── Toast 通知 ──
    window.showToast = function(message, type) {
        type = type || 'info';
        var container = document.getElementById('toastContainer');
        if (!container) return;
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    };

    // ── API 请求封装 ──
    window.api = {
        get: function(url) {
            return fetch(url, { credentials: 'same-origin' })
                .then(function(r) { return r.json(); });
        },
        post: function(url, data) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(data)
            }).then(function(r) { return r.json(); });
        }
    };

    // ── 未读通知角标 ──
    function updateNotifBadge() {
        var badge = document.getElementById('notifBadge');
        if (!badge) return;
        fetch('/notifications/api/notifications/count', { credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.count > 0) {
                    badge.textContent = data.count > 99 ? '99+' : data.count;
                    badge.style.display = '';
                } else {
                    badge.style.display = 'none';
                }
            })
            .catch(function() {});
    }
    updateNotifBadge();
    // 每30秒检查一次未读通知数
    setInterval(updateNotifBadge, 30000);

})();
