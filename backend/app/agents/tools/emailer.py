"""
Email sending tool using SMTP.
"""

import logging
import os
from typing import Dict, Any, Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

logger = logging.getLogger(__name__)


class EmailTool:
    """Tool for sending emails."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
    ):
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.smtp_from = smtp_from or os.getenv("SMTP_FROM", self.smtp_user)

        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not set, email sending will fail")

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send an email.

        Args:
            inputs: Dict with:
                - to: Email address or list of addresses
                - subject: Email subject
                - body: Email body (text or HTML)
                - html: If True, body is HTML (default: False)

        Returns:
            Dict with success status
        """
        to = inputs.get("to")
        subject = inputs.get("subject", "")
        body = inputs.get("body", "")
        is_html = inputs.get("html", False)

        if not to:
            return {"error": "No recipient specified"}

        # Convert single address to list
        if isinstance(to, str):
            to = [to]

        return await self._send_email(to, subject, body, is_html)

    async def _send_email(
        self, to: List[str], subject: str, body: str, is_html: bool = False
    ) -> Dict[str, Any]:
        """Send email via SMTP."""
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

            logger.info(f"Sent email to {to}")
            return {
                "success": True,
                "to": to,
                "subject": subject,
            }

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {"error": str(e)}
