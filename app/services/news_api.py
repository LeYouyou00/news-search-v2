"""NewsAPI.org 新闻搜索集成"""
import logging
import ssl
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 为透过代理的 HTTPS 连接强制 TLS 1.2（部分 Clash 节点不支持 TLS 1.3）
_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = False
_SSL_CONTEXT.verify_mode = ssl.CERT_NONE
_SSL_CONTEXT.minimum_version = ssl.TLSVersion.TLSv1_2
_SSL_CONTEXT.maximum_version = ssl.TLSVersion.TLSv1_2

# 来源权威性分级表
SOURCE_AUTHORITY = {
    # S 级（国际顶级通讯社/官方媒体）
    'reuters': 10, 'associated-press': 10, 'ap': 10, 'afp': 10, 'bloomberg': 10,
    'bbc-news': 10, 'bbc': 10, 'cnn': 10, 'the-new-york-times': 9,
    'xinhua-net': 10, '新华社': 10, 'cctv': 9, '人民日报': 10,
    'the-washington-post': 9, 'the-wall-street-journal': 9, 'wsj': 9,
    'the-guardian': 9, 'al-jazeera-english': 8, 'nhk': 8,
    # A 级（主流媒体）
    'google-news': 8, 'usa-today': 7, 'fox-news': 7, 'msnbc': 7,
    'abc-news': 7, 'nbc-news': 7, 'cbs-news': 7,
    '新浪': 7, '网易': 7, '腾讯': 7, '凤凰': 7, '环球时报': 7,
    'the-independent': 7, 'time': 7, 'forbes': 7,
    'techcrunch': 7, 'the-verge': 7, 'wired': 7, 'ars-technica': 7,
    # B 级
    'business-insider': 6, 'cnbc': 6, 'vice-news': 6,
    'buzzfeed': 5, 'daily-mail': 5, 'the-sun': 4,
    'hacker-news': 6, 'reddit': 3,
}


def get_source_authority(source_name: str) -> float:
    """根据来源名获取权威性评分"""
    name_lower = source_name.lower().strip()
    # 精确匹配
    if name_lower in SOURCE_AUTHORITY:
        return SOURCE_AUTHORITY[name_lower]
    # 模糊匹配
    for key, val in SOURCE_AUTHORITY.items():
        if key in name_lower:
            return val
    return 4.0  # 未知来源默认 4 分


async def search_news(
    keyword: str,
    max_results: int = 100,
    language: str = 'zh',
) -> list[dict]:
    """通过 NewsAPI 搜索新闻

    Args:
        keyword: 搜索关键词
        max_results: 最大结果数
        language: 语言代码

    Returns:
        标准化后的新闻列表 [{'title': ..., 'source': ..., 'url': ..., ...}, ...]
    """
    if not settings.newsapi_available:
        logger.warning('NewsAPI key not configured, using fallback')
        return await _search_news_fallback(keyword, max_results)

    # 计算 24h 前的时间
    from_date = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%d')

    articles = []
    page = 1

    proxy_url = settings.HTTPS_PROXY or settings.HTTP_PROXY or None
    async with httpx.AsyncClient(
        timeout=settings.NEWSAPI_TIMEOUT,
        proxy=proxy_url,
        verify=_SSL_CONTEXT,
    ) as client:
        while len(articles) < max_results and page <= 5:
            params = {
                'q': keyword,
                'from': from_date,
                'sortBy': 'popularity',
                'language': language,
                'pageSize': min(100, max_results - len(articles)),
                'page': page,
                'apiKey': settings.NEWSAPI_KEY,
            }
            try:
                response = await client.get(
                    f'{settings.NEWSAPI_BASE_URL}/everything',
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                if data.get('status') != 'ok':
                    logger.error(f'NewsAPI error: {data.get("message")}')
                    break

                items = data.get('articles', [])
                if not items:
                    break

                for item in items:
                    articles.append({
                        'title': item.get('title', ''),
                        'source_name': item.get('source', {}).get('name', '未知来源'),
                        'source_url': item.get('url', ''),
                        'published_at': item.get('publishedAt', ''),
                        'summary': item.get('description', ''),
                        'author': item.get('author', ''),
                    })

                page += 1

            except httpx.HTTPStatusError as e:
                logger.error(f'NewsAPI HTTP error: {e}')
                # 426 = dev-only restriction，回退到 fallback
                if e.response.status_code == 426:
                    logger.warning('NewsAPI dev-only restriction, using fallback')
                    return await _search_news_fallback(keyword, max_results)
                raise
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
                logger.warning(f'NewsAPI connection failed ({type(e).__name__}: {e}), using fallback')
                return await _search_news_fallback(keyword, max_results)
            except Exception as e:
                logger.error(f'NewsAPI unexpected error: {e}')
                return await _search_news_fallback(keyword, max_results)

    if not articles:
        logger.warning(f'No results from NewsAPI for "{keyword}", trying fallback')
        return await _search_news_fallback(keyword, max_results)

    return articles[:max_results]


async def _search_news_fallback(keyword: str, max_results: int = 20) -> list[dict]:
    """当 NewsAPI 不可用时，使用 DeepSeek 模拟新闻搜索

    注意：为避免 JSON 被 max_tokens 截断，实际请求数量限制为 15 条。
    """
    from app.services.deepseek import call_deepseek, extract_json

    # 限制请求数量，确保 JSON 不会因 token 限制被截断
    request_count = min(max_results, 15)

    prompt = f"""你是一个专业的新闻检索助手。请检索并提供{request_count}条关于"{keyword}"的近期真实新闻。

要求：
1. 提供恰好{request_count}条新闻，每条必须包含：标题(title)、来源(source_name)、发布日期(published_at, 格式YYYY-MM-DD)、简明摘要(summary, 2-3句话)、URL(source_url)
2. 确保新闻来源多样化，包含主流媒体和官方渠道
3. 优先选择最近24小时内发布的新闻
4. 新闻内容必须与关键词高度相关
5. 每条 summary 控制在50字以内，确保 JSON 完整输出

请严格按以下JSON数组格式返回，不要包含任何其他文字：
[
  {{"title": "新闻标题", "source_name": "来源名称", "published_at": "2026-06-09", "summary": "新闻摘要内容...", "source_url": "https://..."}},
  ...
]"""

    try:
        messages = [{'role': 'user', 'content': prompt}]
        raw = await call_deepseek(messages, temperature=0.7, max_tokens=4096)
        articles = extract_json(raw)
        if isinstance(articles, dict):
            articles = articles.get('articles', articles.get('news', [articles]))
        if isinstance(articles, list):
            return articles[:max_results]
        logger.warning(f'Fallback returned unexpected type: {type(articles)}')
        return []
    except Exception as e:
        logger.error(f'Fallback search failed: {e}')
        return []
