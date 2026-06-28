"""購點收據 email 寄送。

設計原則：
- 寄送失敗**不阻擋業務**（PurchaseView 已建單 + 入帳，email 失敗只是少了收據）→ catch 全 exception
- HTML + text 雙版本（不少 mail client 仍只看 plain text）
- 內容固定模板，未來改 template engine 不算 breaking change
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from apps.billing.models import PurchaseOrder

logger = logging.getLogger(__name__)


def _render_receipt_text(order: PurchaseOrder, balance_after: int) -> str:
    lines = [
        "感謝您購買 Argus 點數！",
        "",
        f"訂單編號：#{order.id}",
        f"購買時間：{order.paid_at.strftime('%Y-%m-%d %H:%M:%S') if order.paid_at else '—'}",
        f"方案：{order.plan.name}",
        f"金額：NT$ {order.price_ntd:,}",
        f"入帳點數：+{order.coin_amount:,} coin",
        f"當前餘額：{balance_after:,} coin",
        "",
        f"發票類型：{order.get_invoice_type_display()}",
    ]
    if order.invoice_type == PurchaseOrder.InvoiceType.COMPANY:
        lines.append(f"公司抬頭：{order.company_name}")
        lines.append(f"統一編號：{order.tax_id}")
    elif order.carrier_type and order.carrier_type != PurchaseOrder.CarrierType.CLOUD:
        lines.append(f"載具：{order.get_carrier_type_display()} {order.carrier_id}")
    lines.extend([
        "",
        "─" * 32,
        "Argus AI 網站健檢平台",
        "本收據由系統自動產生，請勿直接回覆。",
    ])
    return "\n".join(lines)


def _render_receipt_html(order: PurchaseOrder, balance_after: int) -> str:
    invoice_block = ""
    if order.invoice_type == PurchaseOrder.InvoiceType.COMPANY:
        invoice_block = (
            f"<tr><td>公司抬頭</td><td>{order.company_name}</td></tr>"
            f"<tr><td>統一編號</td><td>{order.tax_id}</td></tr>"
        )
    elif order.carrier_type and order.carrier_type != PurchaseOrder.CarrierType.CLOUD:
        invoice_block = (
            f"<tr><td>載具</td><td>"
            f"{order.get_carrier_type_display()}：{order.carrier_id}</td></tr>"
        )
    paid_at = order.paid_at.strftime("%Y-%m-%d %H:%M:%S") if order.paid_at else "—"
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<body style="margin:0;padding:24px;background:#0a1535;font-family:-apple-system,'Segoe UI',sans-serif;color:#e2e8f0;">
  <div style="max-width:560px;margin:0 auto;background:rgba(15,23,42,0.95);border:1px solid rgba(103,232,249,0.35);border-radius:14px;padding:32px;box-shadow:0 0 24px rgba(34,211,238,0.18);">
    <h1 style="font-size:24px;color:#67e8f9;margin:0 0 8px;">⟡ ARGUS 購點收據</h1>
    <p style="color:#94a3b8;margin:0 0 24px;">感謝您的購買！以下為您的訂單明細：</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr><td style="padding:8px 0;color:#94a3b8;width:30%;">訂單編號</td><td style="font-weight:600;">#{order.id}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;">購買時間</td><td>{paid_at}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;">方案</td><td style="font-weight:600;">{order.plan.name}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;">金額</td><td style="font-weight:600;color:#f1f5f9;">NT$ {order.price_ntd:,}</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;">入帳點數</td><td style="font-weight:700;color:#67e8f9;">+{order.coin_amount:,} coin</td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;">當前餘額</td><td style="font-weight:600;color:#67e8f9;">{balance_after:,} coin</td></tr>
      <tr><td colspan="2" style="padding:12px 0;border-top:1px dashed rgba(148,163,184,0.35);"></td></tr>
      <tr><td style="padding:8px 0;color:#94a3b8;">發票類型</td><td>{order.get_invoice_type_display()}</td></tr>
      {invoice_block}
    </table>
    <p style="margin:24px 0 0;color:#64748b;font-size:12px;line-height:1.6;">
      Argus AI 網站健檢平台 · 本收據由系統自動產生，請勿直接回覆。<br>
      點數一經入帳不可退費，如有問題請聯絡管理員。
    </p>
  </div>
</body>
</html>"""


def send_purchase_receipt(order: PurchaseOrder, balance_after: int) -> bool:
    """寄送購點收據；失敗時 log 但不 raise（不阻擋 purchase 流程）。

    回傳 True/False 表示寄送結果；呼叫端通常不在意（fire-and-forget），但測試會用到。
    """
    if not order.buyer_email:
        logger.warning("purchase #%s 沒有 buyer_email，跳過寄送收據", order.id)
        return False
    try:
        text = _render_receipt_text(order, balance_after)
        html = _render_receipt_html(order, balance_after)
        message = EmailMultiAlternatives(
            subject=f"[Argus] 訂單 #{order.id} 購點收據 — {order.plan.name}",
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.buyer_email],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        logger.info("purchase #%s 收據已寄至 %s", order.id, order.buyer_email)
        return True
    except Exception:
        logger.exception("purchase #%s 收據寄送失敗", order.id)
        return False
