"""Email delivery service using Resend + Jinja2 + premailer.

Renders HTML email templates with Jinja2, inlines CSS with premailer
for maximum email client compatibility, and sends via Resend API.

Resend's Python SDK is synchronous, so all send calls are wrapped
in asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from jinja2 import Environment, PackageLoader, select_autoescape
from premailer import transform

logger = logging.getLogger(__name__)

# Jinja2 template environment -- loads templates from sophia.notifications.templates
_env = Environment(
    loader=PackageLoader("sophia.notifications", "templates"),
    autoescape=select_autoescape(["html"]),
)


def render_email_template(template_name: str, context: dict) -> str:
    """Render a Jinja2 email template and inline CSS with premailer.

    Args:
        template_name: Template file name (e.g., "performance.html").
        context: Template context variables.

    Returns:
        Final HTML string with CSS inlined for email client compatibility.
    """
    template = _env.get_template(template_name)
    html = template.render(**context)
    # Inline CSS for email client compatibility
    return transform(html)


async def send_performance_report(
    client_email: str,
    client_name: str,
    metrics: dict,
    period: str,
    highlights: list[str] | None = None,
    comparisons: dict | None = None,
) -> Optional[str]:
    """Render and send a performance report email via Resend.

    Args:
        client_email: Recipient email address.
        client_name: Client's business name for personalization.
        metrics: Key metrics dict (engagement_rate, reach, impressions, etc.).
        period: Human-readable period string (e.g., "Week of Feb 17-23, 2026").
        highlights: Optional list of top-performing content highlights.
        comparisons: Optional period-over-period comparison data.

    Returns:
        Resend message ID on success, None on failure.
    """
    try:
        import resend
        from sophia.config import get_settings

        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning("RESEND_API_KEY not configured, skipping email send")
            return None

        resend.api_key = settings.resend_api_key

        html = render_email_template("performance.html", {
            "client_name": client_name,
            "metrics": metrics,
            "period": period,
            "year": datetime.now().year,
            "highlights": highlights or [],
            "comparisons": comparisons or {},
        })

        subject = f"Your Content Performance Report - {period}"
        from_addr = f"{settings.notification_from_name} <{settings.notification_from_email}>"

        params = {
            "from": from_addr,
            "to": [client_email],
            "subject": subject,
            "html": html,
        }

        result = await asyncio.to_thread(resend.Emails.send, params)
        message_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        logger.info(
            "Performance report sent to %s (message_id=%s)",
            client_email,
            message_id,
        )
        return message_id

    except Exception:
        logger.exception("Failed to send performance report to %s", client_email)
        return None


async def send_value_signal_email(
    client_email: str,
    client_name: str,
    headline: str,
    details: str,
    metric_value: float | None = None,
    metric_baseline: float | None = None,
) -> Optional[str]:
    """Render and send a value signal email via Resend.

    Value signals highlight wins -- "Your spring prep post drove 12 enquiries."
    These require operator approval before this function is called.

    Args:
        client_email: Recipient email address.
        client_name: Client's business name.
        headline: Win headline (e.g., "Great news about your spring prep post!").
        details: Supporting context about the win.
        metric_value: The win metric value (e.g., 12 enquiries).
        metric_baseline: Baseline for comparison (e.g., average of 4).

    Returns:
        Resend message ID on success, None on failure.
    """
    try:
        import resend
        from sophia.config import get_settings

        settings = get_settings()
        if not settings.resend_api_key:
            logger.warning("RESEND_API_KEY not configured, skipping email send")
            return None

        resend.api_key = settings.resend_api_key

        # Compute comparison text if baseline available
        comparison_text = None
        if metric_value is not None and metric_baseline is not None and metric_baseline > 0:
            ratio = metric_value / metric_baseline
            comparison_text = f"That's {ratio:.1f}x your average"

        html = render_email_template("value_signal.html", {
            "client_name": client_name,
            "headline": headline,
            "details": details,
            "metric_value": metric_value,
            "metric_baseline": metric_baseline,
            "comparison_text": comparison_text,
            "year": datetime.now().year,
        })

        subject = headline
        from_addr = f"{settings.notification_from_name} <{settings.notification_from_email}>"

        params = {
            "from": from_addr,
            "to": [client_email],
            "subject": subject,
            "html": html,
        }

        result = await asyncio.to_thread(resend.Emails.send, params)
        message_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        logger.info(
            "Value signal email sent to %s (message_id=%s)",
            client_email,
            message_id,
        )
        return message_id

    except Exception:
        logger.exception("Failed to send value signal email to %s", client_email)
        return None
