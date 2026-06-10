"""应用配置管理 — 支持开发/生产环境切换"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 文件
load_dotenv(BASE_DIR / '.env')


class Settings:
    """全局配置"""
    # ── 应用基础 ──
    APP_NAME: str = 'NewsRadar Pro'
    APP_VERSION: str = '2.1.0'
    DEBUG: bool = os.getenv('DEBUG', 'true').lower() == 'true'
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'change-me-in-production-' + os.urandom(16).hex())

    # ── 数据库 ──
    DATABASE_URL: str = os.getenv(
        'DATABASE_URL',
        f'sqlite:///{BASE_DIR}/instance/database.db'
    )
    DB_ECHO: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'

    # ── NewsAPI ──
    NEWSAPI_KEY: str = os.getenv('NEWSAPI_KEY', '')
    NEWSAPI_BASE_URL: str = 'https://newsapi.org/v2'
    NEWSAPI_PAGE_SIZE: int = 100  # 每次获取最多100条
    NEWSAPI_TIMEOUT: int = 8      # 请求超时(秒)，不可达时快速回退到 DeepSeek

    # ── 代理 ──
    HTTP_PROXY: str = os.getenv('HTTP_PROXY', '')
    HTTPS_PROXY: str = os.getenv('HTTPS_PROXY', '')

    # ── DeepSeek API ──
    DEEPSEEK_API_KEY: str = os.getenv('DEEPSEEK_API_KEY', '')
    DEEPSEEK_API_URL: str = 'https://api.deepseek.com/chat/completions'
    DEEPSEEK_MODEL: str = 'deepseek-chat'
    DEEPSEEK_TIMEOUT: int = 90

    # ── 缓存 ──
    CACHE_DIR: str = str(BASE_DIR / 'instance' / 'cache')
    CACHE_TTL_SEARCH: int = 3600  # 搜索缓存1小时

    # ── 邮件 ──
    SMTP_HOST: str = os.getenv('SMTP_HOST', '')
    SMTP_PORT: int = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER: str = os.getenv('SMTP_USER', '')
    SMTP_PASSWORD: str = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM: str = os.getenv('SMTP_FROM', 'noreply@newsradar.com')

    # ── 调度器 ──
    SCHEDULER_MISFIRE_GRACE_TIME: int = 300  # 错过执行宽限期(秒)

    @property
    def newsapi_available(self) -> bool:
        return bool(self.NEWSAPI_KEY)

    @property
    def deepseek_available(self) -> bool:
        return bool(self.DEEPSEEK_API_KEY)

    @property
    def email_available(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)


settings = Settings()
