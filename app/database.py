"""数据库引擎 & 会话管理"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# 确保 instance 目录存在
import os
os.makedirs('instance', exist_ok=True)

# 创建引擎（SQLite WAL 模式提升并发）
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    connect_args={'check_same_thread': False} if 'sqlite' in settings.DATABASE_URL else {},
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

# 为 SQLite 启用 WAL 模式
if 'sqlite' in settings.DATABASE_URL:
    @event.listens_for(engine, 'connect')
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.close()

# 会话工厂
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# 声明式基类
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表（首次启动时调用）"""
    Base.metadata.create_all(bind=engine)
