"""定时推送路由"""
import asyncio
import json
import logging
from datetime import datetime, time, timezone

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.database import SessionLocal
from app.models.schedule import ScheduledTask
from app.models.search import SearchRecord, SearchResultItem
from app.models.notification import Notification
from app.services.scheduler import scheduler_service
from app.services.news_api import search_news
from app.services.scorer import score_articles
from app.services.emailer import send_email
from app.utils.helpers import templates, template_context, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/schedule', tags=['定时推送'])


def _execute_scheduled_push(user_id: int, task_id: int, keyword: str):
    """执行定时推送任务（同步入口，由 APScheduler 线程池调用）

    内部创建独立 event loop 执行异步逻辑，解决 APScheduler
    ThreadPoolExecutor 无法直接运行 async 函数的问题。
    """
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_execute_push(user_id, task_id, keyword))
    finally:
        loop.close()


async def _async_execute_push(user_id: int, task_id: int, keyword: str):
    """执行定时推送任务（异步实现）"""
    from app.database import SessionLocal as _Db
    db = _Db()
    try:
        # 搜索新闻
        articles = await search_news(keyword, max_results=100)
        if not articles:
            logger.warning(f'Scheduled push "{keyword}" found no results')
            return

        # 评分
        scored = await score_articles(articles, keyword)
        top10 = scored[:10]

        # 存入搜索记录
        record = SearchRecord(
            user_id=user_id,
            keyword=keyword,
            source='scheduled',
            status='completed',
            total_found=len(articles),
        )
        db.add(record)
        db.flush()

        for i, a in enumerate(top10):
            item = SearchResultItem(
                search_id=record.id,
                rank=i + 1,
                title=a['title'],
                source_name=a.get('source_name', ''),
                source_url=a.get('source_url', ''),
                published_at=_parse_dt(a.get('published_at')),
                summary=a.get('summary', ''),
                authority_score=a.get('authority_score', 0),
                recency_score=a.get('recency_score', 0),
                relevance_score=a.get('relevance_score', 0),
                engagement_score=a.get('engagement_score', 0),
                total_score=a.get('total_score', 0),
            )
            db.add(item)

        # 创建通知
        titles = '、'.join([a['title'][:20] + '...' for a in top10[:3]])
        notif = Notification(
            user_id=user_id,
            type='scheduled_result',
            title=f'定时推送：{keyword}',
            content=f'您的定时搜索"{keyword}"已完成，找到{len(articles)}条新闻，Top3：{titles}',
            related_search_id=record.id,
        )
        db.add(notif)

        # 更新任务最后执行时间
        task = db.query(ScheduledTask).get(task_id)
        if task:
            task.last_executed_at = datetime.now(timezone.utc)

        db.commit()

        # 发送邮件
        from app.models.user import User as _User
        user = db.query(_User).get(user_id)
        if user:
            subject = f'[NewsRadar Pro] 定时推送：{keyword}'
            body = f'<h2>定时推送结果：{keyword}</h2><p>共找到 {len(articles)} 条新闻，Top10如下：</p><ol>'
            for a in top10:
                body += f'<li><a href="{a.get("source_url", "#")}">{a["title"]}</a> — {a.get("source_name", "")} (评分: {a["total_score"]})</li>'
            body += '</ol><p><a href="#">登录查看详情</a></p>'
            await send_email(user.email, subject, body)

    except Exception as e:
        logger.exception(f'Scheduled push failed: {e}')
    finally:
        db.close()


def _parse_dt(dt_str: str):
    if not dt_str:
        return None
    for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
        try:
            return datetime.strptime(dt_str.replace('Z', ''), fmt)
        except (ValueError, AttributeError):
            continue
    return None


@router.get('', response_class=HTMLResponse)
async def schedule_page(request: Request):
    """定时推送管理页"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url='/auth/login', status_code=302)

    db = SessionLocal()
    try:
        tasks = db.query(ScheduledTask).filter_by(
            user_id=user.id
        ).order_by(ScheduledTask.created_at.desc()).all()

        ctx = template_context(request)
        ctx['tasks'] = [
            {
                'id': t.id,
                'keyword': t.keyword,
                'push_time': t.push_time.strftime('%H:%M'),
                'days_of_week': t.days_of_week,
                'is_active': t.is_active,
                'last_executed_at': t.last_executed_at.strftime('%Y-%m-%d %H:%M') if t.last_executed_at else '从未执行',
            }
            for t in tasks
        ]
        return templates.TemplateResponse('schedule.html', ctx)
    finally:
        db.close()


@router.post('/api/schedule')
async def create_schedule(
    request: Request,
    keyword: str = Form(''),
    push_time: str = Form(''),     # HH:MM
    days_of_week: str = Form('0-6'),  # 0=周日
):
    """创建定时推送任务"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    if not keyword.strip() or not push_time:
        return JSONResponse({'error': '请填写关键词和推送时间'}, status_code=400)

    try:
        hour, minute = map(int, push_time.split(':'))
    except (ValueError, IndexError):
        return JSONResponse({'error': '时间格式无效，请使用 HH:MM 格式'}, status_code=400)

    db = SessionLocal()
    try:
        task = ScheduledTask(
            user_id=user.id,
            keyword=keyword.strip(),
            push_time=time(hour, minute),
            days_of_week=days_of_week,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # 添加到调度器
        job_id = f'push_user_{user.id}_task_{task.id}'
        scheduler_service.add_daily_job(
            job_id=job_id,
            func=_execute_scheduled_push,
            hour=hour,
            minute=minute,
            day_of_week=days_of_week,
            user_id=user.id,
            task_id=task.id,
            keyword=keyword.strip(),
        )

        return JSONResponse({
            'success': True,
            'task_id': task.id,
            'message': f'已创建定时推送：每天 {push_time} 搜索"{keyword.strip()}"',
        })
    except Exception as e:
        logger.exception(f'Create schedule error: {e}')
        return JSONResponse({'error': str(e)}, status_code=500)
    finally:
        db.close()


@router.delete('/api/schedule/{task_id}')
async def delete_schedule(request: Request, task_id: int):
    """删除定时推送任务"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    db = SessionLocal()
    try:
        task = db.query(ScheduledTask).filter_by(
            id=task_id, user_id=user.id
        ).first()
        if not task:
            return JSONResponse({'error': '任务不存在'}, status_code=404)

        # 从调度器移除
        job_id = f'push_user_{user.id}_task_{task.id}'
        scheduler_service.remove_job(job_id)

        db.delete(task)
        db.commit()

        return JSONResponse({'success': True})
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
    finally:
        db.close()
