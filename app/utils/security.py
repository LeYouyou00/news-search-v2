"""安全相关工具函数"""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional


def generate_token() -> str:
    """生成随机令牌"""
    return hashlib.sha256(os.urandom(32)).hexdigest()


def create_session_token(user_id: int, valid_hours: int = 24) -> str:
    """创建会话令牌（简化版，生产环境应使用 JWT）"""
    return generate_token()
