"""
news_emailer.py — Orchestrator: runs all 6 sectors and sends an email per sector.

Public functions:
  send_sector_email(sector_data, date_str)  → sends one HTML email via Gmail SMTP
  run_daily_news()                          → drives the full daily briefing job

Note: run_daily_news() is a plain synchronous function so it can safely be
called via asyncio.to_thread() from the Telegram bot without any event-loop
conflicts. Telegram notifications are sent via the raw HTTP API (requests)
rather than through the async Bot object to avoid cross-thread issues.
"""

import logging
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
import requests

import config
from jobs.email_builder import build_html_email
from jobs.news_researcher import SECTORS, research_sector

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _send_telegram_message(chat_id: str | int, text: str) -> None:
    """Send a Telegram message via the raw Bot API (safe to call from any thread)."""
    if not config.TELEGRAM_BOT_TOKEN or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": int(chat_id), "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Telegram notification failed: {e}")


# ── Email sender ──────────────────────────────────────────────────────────────

def send_sector_email(sector_data: dict, date_str: str) -> None:
    """Build and send the HTML briefing email for one sector via Gmail SMTP."""
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "Gmail is not configured. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env"
        )

    sector_name = sector_data.get("sector_name", "Tech")
    icon = sector_data.get("icon", "📰")
    subject = f"{icon} {sector_name} — {date_str}"

    html_body = build_html_email(sector_data, date_str)
    # Inject the real sender address into the unsubscribe mailto link
    html_body = html_body.replace("{GMAIL_ADDRESS}", config.GMAIL_ADDRESS)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = config.GMAIL_ADDRESS

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        server.send_message(msg)

    logger.info(f"✅ Email sent: {subject}")


# ── Daily job ─────────────────────────────────────────────────────────────────

def run_daily_news() -> None:
    """
    Run the full daily briefing: research all 6 sectors and email each one.

    This is a plain synchronous function. The Telegram bot calls it via
    asyncio.to_thread() so it never blocks the event loop. Any Telegram
    confirmation messages are sent via the raw HTTP API, not the async Bot
    object, to avoid cross-thread event-loop conflicts.
    """
    now_ist = datetime.now(IST)
    date_str = now_ist.strftime("%d %B %Y")  # e.g. "29 March 2025"

    logger.info(f"=== Daily news job started for {date_str} ===")

    success_count = 0
    failed_sectors = []

    for sector in SECTORS:
        sector_name = sector["name"]
        try:
            logger.info(f"Researching: {sector_name} …")
            sector_data = research_sector(sector)

            logger.info(f"Sending email for: {sector_name} …")
            send_sector_email(sector_data, date_str)
            success_count += 1

        except Exception as e:
            logger.error(f"Failed for sector [{sector_name}]: {e}", exc_info=True)
            failed_sectors.append(sector_name)

        time.sleep(3)  # Avoid API rate limits between sectors

    logger.info(f"=== Daily news job done: {success_count}/6 emails sent ===")

    # Send Telegram confirmation via raw HTTP (safe from any thread)
    if config.MY_TELEGRAM_CHAT_ID:
        if failed_sectors:
            note = f"⚠️ Failed sectors: {', '.join(failed_sectors)}"
        else:
            note = "All 6 delivered. ✅"
        _send_telegram_message(
            config.MY_TELEGRAM_CHAT_ID,
            f"📬 Daily briefing done — {success_count}/6 emails sent. {note}",
        )
