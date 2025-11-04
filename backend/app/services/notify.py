"""
Notification service for email and Discord webhooks.
"""

import logging
import os
from typing import Optional
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

logger = logging.getLogger(__name__)


class NotificationService:
    """Sends notifications via email and Discord."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        discord_webhook: Optional[str] = None,
    ):
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.smtp_from = smtp_from or os.getenv("SMTP_FROM", self.smtp_user)
        self.discord_webhook = discord_webhook or os.getenv("DISCORD_WEBHOOK_URL")

    async def send_email(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        is_html: bool = False,
    ) -> bool:
        """
        Send email notification.

        Args:
            to: Recipient email(s)
            subject: Email subject
            body: Email body
            is_html: Whether body is HTML

        Returns:
            True if successful
        """
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP not configured, skipping email")
            return False

        # Convert single address to list
        if isinstance(to, str):
            to = [to]

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = self.smtp_from
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject

            # Attach body
            mime_type = "html" if is_html else "plain"
            msg.attach(MIMEText(body, mime_type))

            # Send via SMTP
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True,
            )

            logger.info(f"Email sent to {to}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def send_discord(self, message: str, username: str = "Agent Factory") -> bool:
        """
        Send Discord webhook notification.

        Args:
            message: Message text
            username: Bot username

        Returns:
            True if successful
        """
        if not self.discord_webhook:
            logger.warning("Discord webhook not configured, skipping")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.discord_webhook,
                    json={
                        "username": username,
                        "content": message,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()

            logger.info("Discord notification sent")
            return True

        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    async def notify_completion(
        self,
        project_id: int,
        project_name: str,
        status: str,
        result_url: str,
        email: Optional[str] = None,
    ) -> None:
        """
        Send completion notification via email and Discord.

        Args:
            project_id: Project ID
            project_name: Project name
            status: Completion status
            result_url: URL to view results
            email: Email address to notify (optional)
        """
        logger.info(f"Sending completion notifications for project {project_id}")

        # Email notification
        if email:
            subject = f"Agent Factory: {project_name} - {status}"
            body = f"""
<h2>Project Completed</h2>

<p><strong>Project:</strong> {project_name}</p>
<p><strong>Status:</strong> {status}</p>

<p><a href="{result_url}">View Results</a></p>

<hr>
<p><small>Agent Factory</small></p>
"""
            await self.send_email(email, subject, body, is_html=True)

        # Discord notification
        discord_message = f"""
🤖 **Agent Factory - Project Completed**

**Project:** {project_name}
**Status:** {status}

🔗 [View Results]({result_url})
"""
        await self.send_discord(discord_message)

    async def notify_approval_needed(
        self,
        run_id: int,
        action: str,
        risk_level: str,
        approval_url: str,
        email: Optional[str] = None,
    ) -> None:
        """
        Send notification that approval is needed.

        Args:
            run_id: Run ID
            action: Action requiring approval
            risk_level: Risk level
            approval_url: URL to approve/reject
            email: Email address to notify (optional)
        """
        logger.info(f"Sending approval needed notification for run {run_id}")

        # Email notification
        if email:
            subject = f"Agent Factory: Approval Required (Risk: {risk_level})"
            body = f"""
<h2>Approval Required</h2>

<p><strong>Run ID:</strong> {run_id}</p>
<p><strong>Action:</strong> {action}</p>
<p><strong>Risk Level:</strong> {risk_level.upper()}</p>

<p><a href="{approval_url}">Review & Approve</a></p>

<hr>
<p><small>Agent Factory</small></p>
"""
            await self.send_email(email, subject, body, is_html=True)

        # Discord notification
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk_level, "⚪")
        discord_message = f"""
{risk_emoji} **Approval Required**

**Run ID:** {run_id}
**Action:** {action}
**Risk:** {risk_level.upper()}

🔗 [Review & Approve]({approval_url})
"""
        await self.send_discord(discord_message)
