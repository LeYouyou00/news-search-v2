"""新闻搜索路由"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.search import SearchRecord, SearchResultItem
from app.models.user import User
from app.services.news_api import search_news
from app.services.scorer import score_articles
from app.utils.helpers import templates, template_context, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/search', tags=['搜索'])


@router.get('/results')
@router.get('/results/{search_id}')
async def search_results_page(request: Request, search_id: int = None):
    """搜索结果页面"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url='/auth/login', status_code=302)

    ctx = template_context(request)
    ctx['search_id'] = search_id
    return templates.TemplateResponse('search_results.html', ctx)


@router.post('/api/search')
async def execute_search(
    request: Request,
    keyword: str = Form(''),
):
    """执行新闻搜索（AJAX 或 Form POST）"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    keyword = keyword.strip()
    if not keyword:
        return JSONResponse({'error': '请输入搜索关键词'}, status_code=400)

    try:
        # Step 1: 搜索新闻
        articles = await search_news(keyword, max_results=100)

        if not articles:
            return JSONResponse({
                'error': f'未找到与"{keyword}"相关的新闻，请尝试其他关键词。'
            }, status_code=404)

        # Step 2: 评分排序
        scored = await score_articles(articles, keyword)
        if not scored:
            return JSONResponse({'error': '评分过程出错'}, status_code=500)

        # 取前10
        top10 = scored[:10]

        # Step 3: 存入数据库
        db = SessionLocal()
        try:
            record = SearchRecord(
                user_id=user.id,
                keyword=keyword,
                source='manual',
                status='completed',
                total_found=len(articles),
            )
            db.add(record)
            db.flush()  # 获取 record.id

            for i, article in enumerate(top10):
                item = SearchResultItem(
                    search_id=record.id,
                    rank=i + 1,
                    title=article['title'],
                    source_name=article.get('source_name', ''),
                    source_url=article.get('source_url', ''),
                    published_at=_parse_datetime(article.get('published_at')),
                    summary=article.get('summary', ''),
                    authority_score=article.get('authority_score', 0),
                    recency_score=article.get('recency_score', 0),
                    relevance_score=article.get('relevance_score', 0),
                    engagement_score=article.get('engagement_score', 0),
                    total_score=article.get('total_score', 0),
                )
                db.add(item)
                db.flush()  # 立即获取 item.id

            db.commit()

            # 从数据库重新查询以获取真实 ID
            saved_items = db.query(SearchResultItem).filter_by(
                search_id=record.id
            ).order_by(SearchResultItem.rank).all()

            return JSONResponse({
                'success': True,
                'search_id': record.id,
                'keyword': keyword,
                'total_found': len(articles),
                'results': [
                    {
                        'id': item.id,
                        'rank': item.rank,
                        'title': item.title,
                        'source_name': item.source_name,
                        'source_url': item.source_url,
                        'published_at': str(item.published_at) if item.published_at else '',
                        'summary': item.summary,
                        'authority_score': item.authority_score,
                        'recency_score': item.recency_score,
                        'relevance_score': item.relevance_score,
                        'engagement_score': item.engagement_score,
                        'total_score': item.total_score,
                    }
                    for item in saved_items
                ],
            })

        finally:
            db.close()

    except Exception as e:
        logger.exception(f'Search error: {e}')
        return JSONResponse({'error': f'搜索失败：{str(e)}'}, status_code=500)


@router.get('/api/results/{search_id}')
async def get_search_results(request: Request, search_id: int):
    """获取已有搜索的结果"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    db = SessionLocal()
    try:
        record = db.query(SearchRecord).filter_by(
            id=search_id, user_id=user.id
        ).first()
        if not record:
            return JSONResponse({'error': '搜索记录不存在'}, status_code=404)

        items = db.query(SearchResultItem).filter_by(
            search_id=search_id
        ).order_by(SearchResultItem.rank).all()

        return JSONResponse({
            'search_id': record.id,
            'keyword': record.keyword,
            'results': [
                {
                    'id': item.id,
                    'rank': item.rank,
                    'title': item.title,
                    'source_name': item.source_name,
                    'source_url': item.source_url,
                    'published_at': str(item.published_at) if item.published_at else '',
                    'summary': item.summary,
                    'authority_score': item.authority_score,
                    'recency_score': item.recency_score,
                    'relevance_score': item.relevance_score,
                    'engagement_score': item.engagement_score,
                    'total_score': item.total_score,
                }
                for item in items
            ],
        })
    finally:
        db.close()


def _parse_datetime(dt_str: str):
    """解析日期字符串"""
    if not dt_str:
        return None
    for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
        try:
            return datetime.strptime(dt_str.replace('Z', ''), fmt)
        except (ValueError, AttributeError):
            continue
    return None
