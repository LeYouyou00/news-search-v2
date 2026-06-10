"""定时推送任务模型"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Time, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ScheduledTask(Base):
    __tablename__ = 'scheduled_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'),
                     nullable=False, index=True)
    keyword = Column(String(200), nullable=False)
    push_time = Column(Time, nullable=False)
    days_of_week = Column(String(20), default='0-6')  # 0=周日, 逗号分隔
    is_active = Column(Boolean, default=True)
    last_executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关联
    user = relationship('User', back_populates='scheduled_tasks')

    def __repr__(self):
        return f'<ScheduledTask "{self.keyword}" @{self.push_time}>'
