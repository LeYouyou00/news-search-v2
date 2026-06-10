"""通知路由"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.database import SessionLocal
from app.models.notification import Notification
from app.utils.helpers import templates, template_context, get_current_user

router = APIRouter(prefix='/notifications', tags=['通知'])


@router.get('', response_class=HTMLResponse)
async def notification_page(request: Request):
    """通知中心"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url='/auth/login', status_code=302)

    db = SessionLocal()
    try:
        notifs = db.query(Notification).filter_by(
            user_id=user.id
        ).order_by(Notification.created_at.desc()).limit(50).all()

        ctx = template_context(request)
        ctx['notifications'] = [
            {
                'id': n.id,
                'type': n.type,
                'title': n.title,
                'content': n.content,
                'is_read': n.is_read,
                'search_id': n.related_search_id,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for n in notifs
        ]
        ctx['unread_count'] = sum(1 for n in notifs if not n.is_read)

        return templates.TemplateResponse('notifications.html', ctx)
    finally:
        db.close()


@router.post('/api/notifications/{notif_id}/read')
async def mark_read(request: Request, notif_id: int):
    """标记通知为已读"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    db = SessionLocal()
    try:
        notif = db.query(Notification).filter_by(
            id=notif_id, user_id=user.id
        ).first()
        if notif:
            notif.is_read = True
            db.commit()
        return JSONResponse({'success': True})
    finally:
        db.close()


@router.get('/api/notifications/count')
async def unread_count(request: Request):
    """获取未读通知数量"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    db = SessionLocal()
    try:
        count = db.query(Notification).filter_by(
            user_id=user.id, is_read=False
        ).count()
        return JSONResponse({'count': count})
    finally:
        db.close()
