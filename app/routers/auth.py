"""用户认证路由：注册/登录/注销"""
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.helpers import templates, template_context

router = APIRouter(prefix='/auth', tags=['认证'])


@router.get('/login', response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse('login.html', template_context(request))


@router.post('/login')
async def login(
    request: Request,
    username: str = Form(''),
    password: str = Form(''),
    privacy_consent: bool = Form(False),
    db: Session = Depends(get_db),
):
    """处理登录"""
    ctx = template_context(request)

    # 必须勾选隐私政策
    if not privacy_consent:
        ctx['error'] = '请先阅读并同意隐私政策。'
        ctx['username'] = username
        return templates.TemplateResponse('login.html', ctx, status_code=400)

    if not username or not password:
        ctx['error'] = '请输入用户名和密码。'
        ctx['username'] = username
        return templates.TemplateResponse('login.html', ctx, status_code=400)

    # 查找用户
    user = db.query(User).filter_by(username=username.strip(), is_active=True).first()
    if not user or not user.verify_password(password):
        ctx['error'] = '用户名或密码错误。'
        ctx['username'] = username
        return templates.TemplateResponse('login.html', ctx, status_code=400)

    # 更新隐私政策同意状态
    if not user.privacy_accepted:
        user.privacy_accepted = True
        user.privacy_accepted_at = datetime.now(timezone.utc)
        db.commit()

    # 设置 session
    request.session['user_id'] = user.id
    request.session['username'] = user.username

    return RedirectResponse(url='/home', status_code=302)


@router.get('/register', response_class=HTMLResponse)
async def register_page(request: Request):
    """注册页面"""
    return templates.TemplateResponse('register.html', template_context(request))


@router.post('/register')
async def register(
    request: Request,
    username: str = Form(''),
    email: str = Form(''),
    password: str = Form(''),
    confirm_password: str = Form(''),
    privacy_consent: bool = Form(False),
    db: Session = Depends(get_db),
):
    """处理注册"""
    ctx = template_context(request)

    # 必须勾选隐私政策
    if not privacy_consent:
        ctx['error'] = '请先阅读并同意隐私政策。'
        ctx['username'] = username
        ctx['email'] = email
        return templates.TemplateResponse('register.html', ctx, status_code=400)

    # 表单验证
    errors = []
    if not username or len(username.strip()) < 3 or len(username.strip()) > 80:
        errors.append('用户名长度需在3-80个字符之间。')
    if not email or '@' not in email.strip():
        errors.append('请输入有效的邮箱地址。')
    if not password or len(password) < 6:
        errors.append('密码长度不能少于6位。')
    if password != confirm_password:
        errors.append('两次输入的密码不一致。')

    if errors:
        ctx['error'] = ' '.join(errors)
        ctx['username'] = username
        ctx['email'] = email
        return templates.TemplateResponse('register.html', ctx, status_code=400)

    username = username.strip()
    email = email.strip()

    # 检查唯一性
    if db.query(User).filter_by(username=username).first():
        ctx['error'] = '该用户名已被注册。'
        ctx['username'] = username
        ctx['email'] = email
        return templates.TemplateResponse('register.html', ctx, status_code=400)

    if db.query(User).filter_by(email=email).first():
        ctx['error'] = '该邮箱已被注册。'
        ctx['username'] = username
        ctx['email'] = email
        return templates.TemplateResponse('register.html', ctx, status_code=400)

    # 创建用户
    user = User(
        username=username,
        email=email,
        privacy_accepted=True,
        privacy_accepted_at=datetime.now(timezone.utc),
    )
    user.set_password(password)
    db.add(user)
    db.commit()

    # 注册成功，跳转登录
    ctx['success'] = '注册成功！请登录。'
    return templates.TemplateResponse('login.html', ctx)


@router.get('/logout')
async def logout(request: Request):
    """注销"""
    request.session.clear()
    return RedirectResponse(url='/auth/login', status_code=302)
