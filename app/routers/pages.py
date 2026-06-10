"""页面路由：首页、隐私政策等"""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from app.utils.helpers import templates, template_context

router = APIRouter(tags=['页面'])


@router.get('/', response_class=HTMLResponse)
async def index(request: Request):
    """根路径：已登录跳转home，未登录跳转login"""
    if request.session.get('user_id'):
        return RedirectResponse(url='/home', status_code=302)
    return RedirectResponse(url='/auth/login', status_code=302)


@router.get('/home', response_class=HTMLResponse)
async def home(request: Request):
    """主页"""
    if not request.session.get('user_id'):
        return RedirectResponse(url='/auth/login', status_code=302)
    return templates.TemplateResponse('home.html', template_context(request))


@router.get('/privacy', response_class=HTMLResponse)
async def privacy(request: Request):
    """隐私政策页面"""
    return templates.TemplateResponse('privacy.html', template_context(request))
