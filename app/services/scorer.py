"""新闻评分引擎"""
import hashlib
import math
import logging
from datetime import datetime, timedelta, timezone

from app.services.deepseek import call_deepseek, extract_json

logger = logging.getLogger(__name__)

# 相关性评分缓存（避免相同关键词+新闻重复调用 DeepSeek）
_relevance_cache: dict[str, float] = {}

# 来源权威性分级
SOURCE_AUTHORITY = {
    'reuters': 10, 'ap': 10, 'bloomberg': 10, 'bbc': 10, 'cnn': 10,
    '新华社': 10, '人民日报': 10, 'cctv': 9, '环球时报': 7,
    '新浪': 7, '网易': 7, '腾讯': 7, '凤凰': 7, '搜狐': 6,
    '36氪': 6, '虎嗅': 6, '澎湃': 7,
    'techcrunch': 7, 'the-verge': 7, 'wired': 7,
}

# 来源月访问量估算（百万，用于互动预估）
SOURCE_TRAFFIC = {
    'reuters': 80, 'ap': 70, 'bloomberg': 60, 'bbc': 100, 'cnn': 120,
    '新华社': 50, '人民日报': 40, 'cctv': 30, '环球时报': 15,
    '新浪': 200, '网易': 150, '腾讯': 180, '凤凰': 50, '搜狐': 80,
    '36氪': 5, '虎嗅': 3, '澎湃': 10,
    'techcrunch': 15, 'the-verge': 20, 'wired': 10,
}


def score_authority(source_name: str) -> float:
    """来源权威性评分 (0-10)"""
    name_lower = source_name.lower().strip()
    if name_lower in SOURCE_AUTHORITY:
        return float(SOURCE_AUTHORITY[name_lower])
    for key, val in SOURCE_AUTHORITY.items():
        if key in name_lower:
            return float(val)
    return 4.0


def score_recency(published_at_str: str) -> float:
    """时效性评分 (0-10)：24h 内线性衰减"""
    try:
        if not published_at_str:
            return 5.0
        # 尝试解析多种日期格式
        for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
            try:
                pub_time = datetime.strptime(published_at_str.replace('Z', ''), fmt)
                pub_time = pub_time.replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            return 5.0

        now = datetime.now(timezone.utc)
        hours_ago = (now - pub_time).total_seconds() / 3600
        if hours_ago < 0:
            return 10.0
        if hours_ago >= 24:
            return 0.0
        return round(10 - (hours_ago / 24) * 10, 2)
    except Exception:
        return 5.0


def score_engagement(source_name: str, title: str) -> float:
    """互动预估评分 (0-10)：基于来源流量和标题信息量"""
    name_lower = source_name.lower().strip()
    traffic = SOURCE_TRAFFIC.get(name_lower, 5.0)
    for key, val in SOURCE_TRAFFIC.items():
        if key in name_lower:
            traffic = val
            break

    # 流量 log 归一化
    traffic_score = min(10, math.log10(max(1, traffic)) * 4)

    # 标题信息量（长度、特殊名词）
    title_score = min(10, len(title) / 10)

    return round(traffic_score * 0.5 + title_score * 0.5, 2)


def calculate_total(
    authority: float,
    recency: float,
    relevance: float,
    engagement: float,
) -> float:
    """计算综合加权总分

    权重：权威性30% + 时效性25% + 相关性25% + 互动预估20%
    """
    return round(authority * 0.30 + recency * 0.25 + relevance * 0.25 + engagement * 0.20, 2)


def _cache_key(keyword: str, title: str) -> str:
    """缓存 key：关键词 + 标题 MD5"""
    raw = f'{keyword.lower().strip()}||{title.lower().strip()}'
    return hashlib.md5(raw.encode()).hexdigest()


async def compute_relevance_scores(articles: list[dict], keyword: str) -> list[float]:
    """使用 DeepSeek 批量计算相关性评分（缓存 + temperature=0 确定性输出）"""
    if not articles:
        return []

    scores = [None] * len(articles)
    uncached_indices = []
    uncached_articles = []

    # 先查缓存
    for i, a in enumerate(articles):
        ck = _cache_key(keyword, a['title'])
        if ck in _relevance_cache:
            scores[i] = _relevance_cache[ck]
        else:
            uncached_indices.append(i)
            uncached_articles.append(a)

    if not uncached_articles:
        return [float(s) for s in scores]

    # 调用 DeepSeek 评分未缓存文章
    try:
        articles_text = '\n\n'.join([
            f'[{j+1}] 标题：{a["title"]}\n摘要：{a.get("summary", "")[:200]}'
            for j, a in enumerate(uncached_articles)
        ])

        prompt = f"""你是一个新闻相关性评估专家。请评估以下{len(uncached_articles)}条新闻与关键词"{keyword}"的相关性。

每条新闻请给出0-10的相关性评分：
- 10分：核心直接相关
- 7-9分：高度相关
- 4-6分：中度相关
- 1-3分：弱相关
- 0分：无关

{articles_text}

请严格按以下JSON数组格式返回，只返回JSON：
[{len(uncached_articles)}个数字)"""

        messages = [{'role': 'user', 'content': prompt}]
        # temperature=0: 确定性输出，相同输入永远相同评分
        raw = await call_deepseek(messages, temperature=0, max_tokens=512)
        new_scores = extract_json(raw)

        if isinstance(new_scores, list) and len(new_scores) == len(uncached_articles):
            for j, idx in enumerate(uncached_indices):
                val = float(new_scores[j])
                scores[idx] = val
                _relevance_cache[_cache_key(keyword, articles[idx]['title'])] = val
        else:
            raise ValueError(f'Unexpected format: {type(new_scores)}')
    except Exception as e:
        logger.warning(f'Relevance scoring via DeepSeek failed: {e}')
        # Fallback：确定性关键词匹配
        keyword_lower = keyword.lower()
        for idx in uncached_indices:
            text = (articles[idx]['title'] + ' ' + articles[idx].get('summary', '')).lower()
            count = text.count(keyword_lower)
            val = min(10.0, count * 2.0 + 3.0)
            scores[idx] = val
            _relevance_cache[_cache_key(keyword, articles[idx]['title'])] = val

    return [float(s) for s in scores]


async def score_articles(articles: list[dict], keyword: str) -> list[dict]:
    """对文章列表进行综合评分并排序

    Args:
        articles: 新闻列表
        keyword: 搜索关键词

    Returns:
        按 total_score 降序排列的新闻列表（最多10条）
    """
    if not articles:
        return []

    # 去重：按标题相似度去重（保留先出现的）
    seen_titles = set()
    deduped = []
    for a in articles:
        # 规范化标题用于比较：转小写、去空格、去标点
        title_norm = ''.join(c.lower() for c in a.get('title', '') if c.isalnum())
        if title_norm and title_norm not in seen_titles:
            seen_titles.add(title_norm)
            deduped.append(a)
        elif not title_norm:
            deduped.append(a)  # 标题为空的文章保留

    if len(deduped) < len(articles):
        logger.info(f'Deduplication: {len(articles)} -> {len(deduped)} articles')

    articles = deduped

    # 计算各项评分
    relevance_scores = await compute_relevance_scores(articles, keyword)

    scored = []
    for i, article in enumerate(articles):
        authority = score_authority(article.get('source_name', ''))
        recency = score_recency(article.get('published_at', ''))
        relevance = relevance_scores[i] if i < len(relevance_scores) else 5.0
        engagement = score_engagement(
            article.get('source_name', ''),
            article.get('title', ''),
        )
        total = calculate_total(authority, recency, relevance, engagement)

        scored.append({
            **article,
            'authority_score': authority,
            'recency_score': recency,
            'relevance_score': relevance,
            'engagement_score': engagement,
            'total_score': total,
        })

    # 按总分降序排列，取前10
    scored.sort(key=lambda x: x['total_score'], reverse=True)
    return scored[:10]
