"""通知模型"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'),
                     nullable=False, index=True)
    type = Column(String(20), nullable=False, default='scheduled_result')  # scheduled_result / system
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    related_search_id = Column(Integer, ForeignKey('search_records.id', ondelete='SET NULL'),
                               nullable=True)
    is_read = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # 关联
    user = relationship('User', back_populates='notifications')

    def __repr__(self):
        return f'<Notification "{self.title}" for user_{self.user_id}>'
