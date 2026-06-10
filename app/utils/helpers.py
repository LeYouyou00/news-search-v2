"""通用工具函数"""
from fastapi import Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Jinja2 模板引擎
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'templates'
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def get_current_user(request: Request):
    """从 session 加载当前登录用户"""
    from app.database import SessionLocal
    from app.models.user import User

    user_id = request.session.get('user_id')
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).get(user_id)
    finally:
        db.close()


def flash_message(request: Request, message: str, category: str = 'info'):
    """设置 flash 消息"""
    if '_flashes' not in request.session:
        request.session['_flashes'] = []
    request.session['_flashes'].append({'message': message, 'category': category})


def get_flash_messages(request: Request) -> list:
    """获取并清除 flash 消息"""
    return request.session.pop('_flashes', [])


def template_context(request: Request, **kwargs) -> dict:
    """构建模板渲染上下文"""
    from app.config import settings

    user = get_current_user(request)
    return {
        'request': request,
        'user': user,
        'app_name': settings.APP_NAME,
        'app_version': settings.APP_VERSION,
        'flash_messages': get_flash_messages(request),
        **kwargs,
    }
