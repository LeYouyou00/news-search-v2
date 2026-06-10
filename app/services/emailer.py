"""邮件发送服务"""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, body_html: str) -> bool:
    """发送邮件（异步）

    Args:
        to_email: 收件人邮箱
        subject: 邮件主题
        body_html: HTML 邮件正文

    Returns:
        是否发送成功
    """
    if not settings.email_available:
        logger.warning('SMTP not configured, skipping email to %s', to_email)
        return False

    try:
        import aiosmtplib

        msg = MIMEMultipart('alternative')
        msg['From'] = settings.SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=True,
        )
        logger.info('Email sent to %s', to_email)
        return True
    except Exception as e:
        logger.error('Failed to send email to %s: %s', to_email, e)
        return False
