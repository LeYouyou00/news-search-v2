"""FastAPI 应用工厂"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db
from app.services.scheduler import scheduler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    init_db()
    scheduler_service.start()
    yield
    scheduler_service.shutdown()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # Session 中间件（必须最先添加）
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    # 静态文件（Cache-Control: 开发环境禁用缓存）
    import os as _os
    _cache_seconds = 0 if settings.DEBUG else 3600
    static_dir = Path(__file__).parent / 'static'
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')
    # 添加响应头禁用静态资源缓存（开发模式）
    if settings.DEBUG:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request as _Request
        class _NoCacheStaticMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: _Request, call_next):
                response = await call_next(request)
                if request.url.path.startswith('/static/'):
                    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    response.headers['Pragma'] = 'no-cache'
                    response.headers['Expires'] = '0'
                return response
        app.add_middleware(_NoCacheStaticMiddleware)

    # 注册路由
    from app.routers import auth, search, analyze, schedule, notification, pages
    app.include_router(auth.router)
    app.include_router(search.router)
    app.include_router(analyze.router)
    app.include_router(schedule.router)
    app.include_router(notification.router)
    app.include_router(pages.router)

    return app
