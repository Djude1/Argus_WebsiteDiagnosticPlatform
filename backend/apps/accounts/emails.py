"""accounts 模組的 email 寄送（重設密碼信等）。

設計原則：
- 失敗不阻擋業務（password reset request 端點要永遠回成功，避免洩漏 email 註冊狀態）
- text + HTML 雙版本
- 文案直白，避免「AI 廢話」
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def _build_reset_link(base_url: str, token: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/password-reset/confirm?token={token}"


def _render_reset_text(email: str, link: str, expires_minutes: int) -> str:
    return (
        "您好，\n\n"
        f"有人為您的 Argus 帳號（{email}）要求重設密碼。\n"
        f"若是您本人，請於 {expires_minutes} 分鐘內點下方連結重設：\n\n"
        f"{link}\n\n"
        "若您沒有提出這個要求，請忽略本信；您的密碼不會變動。\n"
        "若這封信不是您預期收到的，建議您確認帳號近期的登入紀錄。\n\n"
        "Argus AI 網站健檢平台\n"
        "本信由系統自動產生，請勿直接回覆。\n"
    )


def _render_reset_html(email: str, link: str, expires_minutes: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<body style="margin:0;padding:24px;background:#0a1535;font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;">
  <div style="max-width:560px;margin:0 auto;background:rgba(15,23,42,0.95);border:1px solid rgba(103,232,249,0.35);border-radius:14px;padding:32px;box-shadow:0 0 24px rgba(34,211,238,0.18);">
    <div style="font-size:13px;letter-spacing:0.2em;color:#67e8f9;margin-bottom:6px;">ARGUS · 帳號安全</div>
    <h1 style="font-size:22px;color:#f1f5f9;margin:0 0 16px;">重設您的密碼</h1>
    <p style="margin:0 0 16px;line-height:1.7;color:#cbd5e1;">
      有人為您的 Argus 帳號 <strong style="color:#f1f5f9;">{email}</strong> 要求重設密碼。
      若是您本人，請於 <strong style="color:#fbbf24;">{expires_minutes} 分鐘內</strong>點下方按鈕完成重設：
    </p>
    <p style="margin:24px 0;">
      <a href="{link}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#06b6d4 0%,#6366f1 100%);color:#fff;text-decoration:none;border-radius:10px;font-weight:600;box-shadow:0 6px 18px rgba(99,102,241,0.45);">
        重設密碼
      </a>
    </p>
    <p style="margin:0 0 8px;font-size:12px;color:#94a3b8;">按鈕點不動？把以下連結貼到瀏覽器網址列：</p>
    <p style="margin:0 0 24px;word-break:break-all;font-size:12px;color:#67e8f9;">{link}</p>
    <div style="border-top:1px dashed rgba(148,163,184,0.35);padding-top:16px;margin-top:24px;font-size:12px;line-height:1.7;color:#64748b;">
      若您<strong style="color:#fbbf24;">沒有</strong>提出這個要求，請忽略本信，您的密碼不會變動。<br>
      若這封信不是您預期的，建議您確認帳號最近的登入紀錄。<br><br>
      Argus AI 網站健檢平台 · 本信由系統自動產生，請勿直接回覆。
    </div>
  </div>
</body>
</html>"""


def send_password_reset_email(
    user_email: str,
    token: str,
    base_url: str,
    expires_minutes: int = 60,
) -> bool:
    """寄送重設密碼信。

    失敗只 log，不 raise：password reset 端點要對「存在 / 不存在的 email」都
    回相同訊息以避免帳號 enumeration，因此寄信失敗也不能讓 view 端看出來。
    """
    if not user_email:
        return False
    try:
        link = _build_reset_link(base_url, token)
        text = _render_reset_text(user_email, link, expires_minutes)
        html = _render_reset_html(user_email, link, expires_minutes)
        message = EmailMultiAlternatives(
            subject="[Argus] 重設您的密碼",
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        logger.info("password reset 信已寄至 %s", user_email)
        return True
    except Exception:
        logger.exception("password reset 信寄送失敗 to=%s", user_email)
        return False
