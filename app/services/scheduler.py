"""APScheduler 定时任务管理服务"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from app.config import settings
from app.database import engine

logger = logging.getLogger(__name__)


class SchedulerService:
    """定时任务调度服务（单例）"""

    def __init__(self):
        jobstores = {}
        # 尝试使用数据库持久化（如果数据库可用）
        try:
            jobstores['default'] = SQLAlchemyJobStore(engine=engine)
        except Exception as e:
            logger.warning(f'Cannot use DB jobstore: {e}, falling back to memory')
            jobstores['default'] = None  # APScheduler 默认使用 memory

        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors={'default': ThreadPoolExecutor(max_workers=5)},
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': settings.SCHEDULER_MISFIRE_GRACE_TIME,
            },
            timezone='Asia/Shanghai',
        )

    def start(self):
        """启动调度器"""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info('Scheduler started')

    def shutdown(self):
        """关闭调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info('Scheduler shutdown')

    def add_daily_job(self, job_id: str, func, hour: int, minute: int, day_of_week: str = '0-6', **kwargs):
        """添加每日定时任务

        Args:
            job_id: 任务唯一ID (如 'push_user_3_task_5')
            func: 任务回调函数（必须是同步函数；异步函数请先包装）
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            day_of_week: 每周哪几天, 如 '0-6' 或 '1,3,5' (0=周日)
            **kwargs: 传递给 func 的参数
        """
        days = day_of_week or '0-6'
        self._scheduler.add_job(
            func,
            trigger='cron',
            id=job_id,
            hour=hour,
            minute=minute,
            day_of_week=days,
            kwargs=kwargs,
            replace_existing=True,
        )

    def remove_job(self, job_id: str):
        """移除定时任务"""
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    def get_job(self, job_id: str):
        """获取定时任务"""
        return self._scheduler.get_job(job_id)


# 全局单例
scheduler_service = SchedulerService()
