/**
 * NewsRadar Pro — 搜索 & 流式分析前端
 */
(function() {
    'use strict';

    // ── 从 URL 获取 keyword 或 search_id 并触发搜索 ──
    var params = new URLSearchParams(window.location.search);
    var keyword = params.get('keyword');

    // 路径 /search/results/{search_id} → 加载历史结果
    var pathMatch = window.location.pathname.match(/\/search\/results\/(\d+)/);
    var searchIdFromPath = pathMatch ? parseInt(pathMatch[1]) : null;

    if (searchIdFromPath) {
        loadHistoryResults(searchIdFromPath);
    } else if (keyword) {
        performSearch(keyword);
    }

    function performSearch(keyword) {
        var container = document.getElementById('resultsContainer');
        if (!container) return;

        container.innerHTML = renderLoading('正在搜索 "' + keyword + '"...');

        var formData = new FormData();
        formData.append('keyword', keyword);

        fetch('/search/api/search', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) {
                container.innerHTML = renderError(data.error);
                return;
            }
            renderResults(data);
        })
        .catch(function(err) {
            container.innerHTML = renderError('网络错误：' + err.message);
        });
    }

    function loadHistoryResults(searchId) {
        var container = document.getElementById('resultsContainer');
        if (!container) return;

        container.innerHTML = renderLoading('正在加载历史搜索结果...');

        fetch('/search/api/results/' + searchId, { credentials: 'same-origin' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    container.innerHTML = renderError(data.error);
                    return;
                }
                renderResults(data);
            })
            .catch(function(err) {
                container.innerHTML = renderError('加载失败：' + err.message);
            });
    }

    function renderResults(data) {
        var container = document.getElementById('resultsContainer');
        var html = '<div class="results-meta">' +
            '<h2>🔍 "' + data.keyword + '" — 搜索结果</h2>' +
            '<p>从 ' + data.total_found + ' 条新闻中筛选 Top ' + data.results.length + '</p>' +
            '</div>' +
            '<div class="results-grid">';

        data.results.forEach(function(item, i) {
            var rankClass = i === 0 ? 'rank-gold' : i === 1 ? 'rank-silver' : i === 2 ? 'rank-bronze' : '';
            html += '<div class="result-card ' + rankClass + '">' +
                '<div class="card-select">' +
                    '<input type="checkbox" class="select-article" value="' + item.id + '" id="sel_' + i + '">' +
                    '<label for="sel_' + i + '"></label>' +
                '</div>' +
                '<div class="card-rank">#' + item.rank + '</div>' +
                '<div class="card-body">' +
                    '<h3><a href="' + (item.source_url || '#') + '" target="_blank">' + item.title + '</a></h3>' +
                    '<div class="card-meta">' +
                        '<span>📰 ' + item.source_name + '</span>' +
                        '<span>📅 ' + (item.published_at || '未知') + '</span>' +
                        '<span class="score-badge">⭐ ' + item.total_score + '</span>' +
                    '</div>' +
                    '<p class="card-summary">' + (item.summary || '暂无摘要') + '</p>' +
                    '<div class="score-breakdown">' +
                        '<span>权威性: ' + item.authority_score + '</span>' +
                        '<span>时效性: ' + item.recency_score + '</span>' +
                        '<span>相关性: ' + item.relevance_score + '</span>' +
                        '<span>互动: ' + item.engagement_score + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>';
        });

        html += '</div>' +
            '<div class="analysis-bar" id="analysisBar">' +
                '<p>已选择 <strong id="selectedCount">0</strong> 条新闻</p>' +
                '<button class="btn btn-analyze" id="analyzeBtn" disabled onclick="startAnalysis(' + data.search_id + ')">' +
                    '📊 深度分析选中新闻' +
                '</button>' +
            '</div>';

        container.innerHTML = html;
        bindCheckboxes();
    }

    function bindCheckboxes() {
        var checkboxes = document.querySelectorAll('.select-article');
        var countEl = document.getElementById('selectedCount');
        var btn = document.getElementById('analyzeBtn');

        checkboxes.forEach(function(cb) {
            cb.addEventListener('change', function() {
                var count = document.querySelectorAll('.select-article:checked').length;
                countEl.textContent = count;
                btn.disabled = count === 0;
                btn.style.opacity = count === 0 ? '0.5' : '1';
            });
        });
    }

    // ═══════════════════════════════════════════════════
    //  流式深度分析 — ChatGPT 风格渐进展示
    // ═══════════════════════════════════════════════════
    window.startAnalysis = function(searchId) {
        var checked = document.querySelectorAll('.select-article:checked');
        var ids = Array.from(checked).map(function(cb) { return cb.value; });

        if (ids.length === 0) {
            showToast('请至少选择一条新闻', 'error');
            return;
        }

        var btn = document.getElementById('analyzeBtn');
        btn.disabled = true;
        btn.textContent = '⏳ 分析中...';

        // 创建报告面板
        var panel = createAnalysisPanel();

        var formData = new FormData();
        formData.append('search_id', searchId);
        formData.append('selected_ids', ids.join(','));

        fetch('/report/api/analyze/stream', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        })
        .then(function(response) {
            if (!response.ok) {
                return response.json().then(function(d) { throw new Error(d.error || '请求失败'); });
            }

            var reader = response.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';
            var sectionMap = {};  // id -> section data
            var reportId = null;

            function processStream() {
                return reader.read().then(function(result) {
                    if (result.done) {
                        finishAnalysis(btn, reportId);
                        return;
                    }

                    buffer += decoder.decode(result.value, { stream: true });
                    var lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i].trim();
                        if (!line.startsWith('data: ')) continue;

                        try {
                            var data = JSON.parse(line.substring(6));

                            switch (data.type) {
                                case 'plan':
                                    // 收到章节计划，创建占位卡片
                                    buildPlaceholders(data.sections);
                                    break;

                                case 'section':
                                    // 一个章节完成，渲染到对应卡片
                                    sectionMap[data.id] = data;
                                    renderSection(data);
                                    updateProgress(data.done_count, data.total);
                                    break;

                                case 'done':
                                    reportId = data.report_id;
                                    break;

                                case 'error':
                                    showToast(data.message, 'error');
                                    break;
                            }
                        } catch (e) {
                            // 跳过解析失败的行
                        }
                    }

                    return processStream();
                });
            }

            return processStream();
        })
        .catch(function(err) {
            showToast('分析请求失败：' + err.message, 'error');
            finishAnalysis(btn, null);
        });
    };

    // ── 报告面板 ──
    function createAnalysisPanel() {
        var existing = document.getElementById('analysisPanel');
        if (existing) existing.remove();

        var panel = document.createElement('div');
        panel.id = 'analysisPanel';
        panel.className = 'analysis-panel';
        panel.innerHTML =
            '<div class="ap-header">' +
                '<h3>🔬 深度分析报告</h3>' +
                '<span class="ap-status" id="apStatus">' +
                    '<span class="ap-pulse"></span> 准备中...' +
                '</span>' +
                '<button class="ap-close" onclick="closeAnalysis()">✕</button>' +
            '</div>' +
            '<div class="ap-sections" id="apSections"></div>' +
            '<div class="ap-footer" id="apFooter" style="display:none">' +
                '<a href="#" class="btn btn-primary" id="apReportLink">📄 查看完整报告</a>' +
            '</div>';

        var resultsGrid = document.querySelector('.results-grid');
        if (resultsGrid) {
            resultsGrid.after(panel);
        } else {
            document.querySelector('.results-meta').after(panel);
        }
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return panel;
    }

    function buildPlaceholders(sections) {
        var container = document.getElementById('apSections');
        if (!container) return;
        container.innerHTML = '';

        sections.forEach(function(sec) {
            var card = document.createElement('div');
            card.className = 'ap-card ap-card--pending';
            card.id = 'apCard_' + sec.id;
            card.innerHTML =
                '<div class="ap-card-head">' +
                    '<span class="ap-card-icon">' + sec.icon + '</span>' +
                    '<h4>' + sec.title + '</h4>' +
                    '<span class="ap-card-status"><span class="ap-dot"></span> 等待生成</span>' +
                '</div>' +
                '<div class="ap-card-body"></div>';
            container.appendChild(card);
        });

        document.getElementById('apStatus').innerHTML =
            '<span class="ap-spinner"></span> 并行生成中... 0/' + sections.length;
    }

    function renderSection(section) {
        var card = document.getElementById('apCard_' + section.id);
        if (!card) return;

        // 切换状态
        card.className = 'ap-card ap-card--active';
        var statusEl = card.querySelector('.ap-card-status');
        statusEl.innerHTML = '✅ 完成';
        statusEl.style.color = '#22c55e';

        // 渲染内容（简单 Markdown → HTML）
        var body = card.querySelector('.ap-card-body');
        body.innerHTML = simpleMarkdown(section.content);

        // 动画
        card.style.animation = 'none';
        card.offsetHeight; // reflow
        card.style.animation = 'cardReveal 0.4s ease';
    }

    function updateProgress(done, total) {
        var status = document.getElementById('apStatus');
        if (status) {
            status.innerHTML = '<span class="ap-spinner"></span> 并行生成中... ' + done + '/' + total;
        }
    }

    function finishAnalysis(btn, reportId) {
        var status = document.getElementById('apStatus');
        if (status) {
            status.innerHTML = '✅ 分析完成';
            status.style.color = '#22c55e';
        }

        // 显示底部链接
        var footer = document.getElementById('apFooter');
        if (footer && reportId) {
            footer.style.display = 'block';
            document.getElementById('apReportLink').href = '/report/' + reportId;
        }

        if (btn) {
            btn.disabled = false;
            btn.textContent = '📊 深度分析选中新闻';
        }
    }

    window.closeAnalysis = function() {
        var panel = document.getElementById('analysisPanel');
        if (panel) panel.remove();
    };

    // ── 简易 Markdown 渲染 ──
    function simpleMarkdown(text) {
        var html = text
            // 转义 HTML
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            // 粗体
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // 换行 → <br> 或 <p>
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            // 编号列表
            .replace(/(\d+)\.\s/g, '<br><strong>$1.</strong> ');
        return '<p>' + html + '</p>';
    }

    // ── 辅助 ──
    function renderLoading(msg) {
        return '<div class="search-loading"><div class="spinner-lg"></div><p>' + msg + '</p></div>';
    }

    function renderError(msg) {
        return '<div class="search-error"><p>⚠️ ' + msg + '</p><a href="/home" class="btn btn-back">返回首页</a></div>';
    }

})();
