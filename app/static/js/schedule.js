/**
 * NewsRadar Pro — 定时推送管理前端
 */
(function() {
    'use strict';

    var form = document.getElementById('scheduleForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var keyword = document.getElementById('schKeyword').value.trim();
            var time = document.getElementById('schTime').value;
            var days = document.getElementById('schDays').value;

            if (!keyword || !time) {
                showToast('请填写关键词和推送时间', 'error');
                return;
            }

            var formData = new FormData();
            formData.append('keyword', keyword);
            formData.append('push_time', time);
            formData.append('days_of_week', days);

            fetch('/schedule/api/schedule', {
                method: 'POST',
                body: formData,
                credentials: 'same-origin'
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    showToast(data.error, 'error');
                    return;
                }
                showToast(data.message, 'success');
                setTimeout(function() { location.reload(); }, 1000);
            })
            .catch(function(err) {
                showToast('请求失败：' + err.message, 'error');
            });
        });
    }

    // 删除任务
    var deleteBtns = document.querySelectorAll('.btn-delete');
    deleteBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            var taskId = this.dataset.taskId;
            if (!confirm('确定删除此定时推送任务？')) return;

            fetch('/schedule/api/schedule/' + taskId, {
                method: 'DELETE',
                credentials: 'same-origin'
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    showToast(data.error, 'error');
                    return;
                }
                showToast('已删除', 'success');
                setTimeout(function() { location.reload(); }, 800);
            });
        });
    });

})();
