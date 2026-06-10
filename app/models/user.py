"""用户模型"""
import bcrypt
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    privacy_accepted = Column(Boolean, nullable=False, default=False)
    privacy_accepted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # 关联
    searches = relationship('SearchRecord', back_populates='user',
                            cascade='all, delete-orphan', lazy='dynamic')
    scheduled_tasks = relationship('ScheduledTask', back_populates='user',
                                   cascade='all, delete-orphan', lazy='dynamic')
    notifications = relationship('Notification', back_populates='user',
                                 cascade='all, delete-orphan', lazy='dynamic')
    analysis_reports = relationship('AnalysisReport', back_populates='user',
                                    cascade='all, delete-orphan', lazy='dynamic')

    def set_password(self, password: str):
        # bcrypt 要求密码不超过 72 字节
        pwd_bytes = password.encode('utf-8')[:72]
        self.password_hash = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password: str) -> bool:
        pwd_bytes = password.encode('utf-8')[:72]
        return bcrypt.checkpw(pwd_bytes, self.password_hash.encode('utf-8'))

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self):
        return f'<User {self.username}>'
