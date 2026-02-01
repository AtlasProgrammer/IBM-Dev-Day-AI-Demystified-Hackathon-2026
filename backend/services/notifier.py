from __future__ import annotations

import json
import smtplib
import sys
from email.message import EmailMessage

import httpx

from backend.core.config import settings


def _print_safe(text: str) -> None:
    enc = sys.stdout.encoding or "utf-8"
    safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
    print(safe)


class Notifier:
    async def send_email(self, *, to: str, subject: str, body: str) -> None:
        raise NotImplementedError

    async def send_slack(self, *, text: str) -> None:
        raise NotImplementedError


class MockNotifier(Notifier):
    async def send_email(self, *, to: str, subject: str, body: str) -> None:
        _print_safe(
            "\n".join(
                [
                    "",
                    "=== MOCK EMAIL ===",
                    f"TO: {to}",
                    f"SUBJECT: {subject}",
                    body,
                    "=== /MOCK EMAIL ===",
                    "",
                ]
            )
        )

    async def send_slack(self, *, text: str) -> None:
        _print_safe("\n".join(["", "=== MOCK SLACK ===", text, "=== /MOCK SLACK ===", ""]))


class SlackWebhookNotifier(Notifier):
    async def send_email(self, *, to: str, subject: str, body: str) -> None:
        if not settings.smtp_host:
            await MockNotifier().send_email(to=to, subject=subject, body=body)
            return

        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)

    async def send_slack(self, *, text: str) -> None:
        if not settings.slack_webhook_url:
            await MockNotifier().send_slack(text=text)
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                settings.slack_webhook_url,
                content=json.dumps({"text": text}),
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()


def get_notifier() -> Notifier:
    if settings.mock_email or settings.mock_slack:
        return MockNotifier()
    return SlackWebhookNotifier()

