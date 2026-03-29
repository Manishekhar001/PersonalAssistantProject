"""
All tools available to the personal assistant agent.
Each tool is a plain Python function decorated with @tool.
The agent decides which tool to call based on the user's message.
"""

import sqlite3
import imaplib
import smtplib
import email
from email.header import decode_header
from email.mime.text import MIMEText
from datetime import datetime

from langchain_core.tools import tool
from serpapi import GoogleSearch
from notion_client import Client

import config

# ── Notion client (shared across Notion tools) ────────────────────────────────
notion = Client(auth=config.NOTION_API_KEY) if config.NOTION_API_KEY else None


# ─────────────────────────────────────────────────────────────────────────────
# 1. WEB SEARCH
# ─────────────────────────────────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """Search the web for current information, news, facts, or anything external."""
    try:
        search = GoogleSearch({
            "q": query,
            "api_key": config.SERPAPI_API_KEY,
            "num": 5,
            "gl": "in",      # India results
            "hl": "en",
        })
        results = search.get_dict().get("organic_results", [])
        if not results:
            return "No search results found."
        return "\n\n".join(
            f"**{r.get('title')}**\n{r.get('snippet', '')}"
            for r in results[:5]
        )
    except Exception as e:
        return f"Web search failed: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. WEATHER
# ─────────────────────────────────────────────────────────────────────────────

@tool
def get_weather(city: str = "Hyderabad") -> str:
    """
    Get current weather for a city.
    city: name of the city (default: Hyderabad)
    """
    try:
        import urllib.request
        url = f"https://wttr.in/{city}?format=3"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = response.read().decode("utf-8").strip()
            return data if data else f"No weather data for {city}."
    except Exception as e:
        return f"Could not fetch weather: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. GMAIL — READ
# ─────────────────────────────────────────────────────────────────────────────

@tool
def read_emails(limit: int = 5) -> str:
    """
    Read the most recent emails from Gmail inbox.
    limit: how many emails to fetch (default 5, max 10).
    """
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        return "Gmail is not configured. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env"
    try:
        limit = min(limit, 10)
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        mail.select("inbox")

        _, ids = mail.search(None, "ALL")
        email_ids = ids[0].split()[-limit:]

        results = []
        for eid in reversed(email_ids):
            _, data = mail.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])

            # Decode subject
            raw_subject, enc = decode_header(msg["Subject"] or "No Subject")[0]
            subject = raw_subject.decode(enc or "utf-8") if isinstance(raw_subject, bytes) else raw_subject

            sender = msg.get("From", "Unknown")
            date = msg.get("Date", "")

            # Extract plain text body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            results.append(
                f"From: {sender}\nDate: {date}\nSubject: {subject}\n\n{body[:400].strip()}"
            )

        mail.close()
        mail.logout()
        return "\n\n" + ("─" * 40 + "\n\n").join(results) if results else "Inbox is empty."

    except Exception as e:
        return f"Could not read emails: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. GMAIL — SEND
# ─────────────────────────────────────────────────────────────────────────────

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email via Gmail.
    to: recipient email address
    subject: email subject line
    body: email body (plain text)
    """
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        return "Gmail is not configured. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env"
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = config.GMAIL_ADDRESS
        msg["To"] = to

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)

        return f"✅ Email sent to {to} with subject '{subject}'."
    except Exception as e:
        return f"Failed to send email: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. NOTION — NOTES
# ─────────────────────────────────────────────────────────────────────────────

@tool
def create_note(title: str, content: str) -> str:
    """
    Create a new note (Notion page) under your Notes section.
    title: note title
    content: note body text
    """
    if not notion or not config.NOTION_NOTES_PAGE_ID:
        return "Notion notes not configured. Add NOTION_API_KEY and NOTION_NOTES_PAGE_ID to .env"
    try:
        notion.pages.create(
            parent={"page_id": config.NOTION_NOTES_PAGE_ID},
            properties={
                "title": {"title": [{"text": {"content": title}}]}
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                }
            ],
        )
        return f"✅ Note '{title}' created in Notion."
    except Exception as e:
        return f"Failed to create note: {str(e)}"


@tool
def get_notes() -> str:
    """Get a list of all notes from your Notion notes page."""
    if not notion or not config.NOTION_NOTES_PAGE_ID:
        return "Notion notes not configured."
    try:
        results = notion.blocks.children.list(block_id=config.NOTION_NOTES_PAGE_ID)
        pages = [
            b for b in results["results"]
            if b["type"] == "child_page"
        ]
        if not pages:
            return "No notes found."
        return "\n".join(
            f"- {p['child_page']['title']}" for p in pages
        )
    except Exception as e:
        return f"Failed to fetch notes: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. NOTION — TASKS
# ─────────────────────────────────────────────────────────────────────────────

@tool
def create_task(title: str, due_date: str = "") -> str:
    """
    Create a new task in your Notion tasks database.
    title: task name
    due_date: optional, format YYYY-MM-DD (e.g. 2025-12-31)
    """
    if not notion or not config.NOTION_TASKS_DB_ID:
        return "Notion tasks not configured. Add NOTION_TASKS_DB_ID to .env"
    try:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Status": {"select": {"name": "Not started"}},
        }
        if due_date:
            properties["Due Date"] = {"date": {"start": due_date}}

        notion.pages.create(
            parent={"database_id": config.NOTION_TASKS_DB_ID},
            properties=properties,
        )
        return f"✅ Task '{title}' created."
    except Exception as e:
        return f"Failed to create task: {str(e)}"


@tool
def get_tasks() -> str:
    """Get all pending (not done) tasks from your Notion tasks database."""
    if not notion or not config.NOTION_TASKS_DB_ID:
        return "Notion tasks not configured."
    try:
        results = notion.databases.query(
            database_id=config.NOTION_TASKS_DB_ID,
            filter={
                "property": "Status",
                "select": {"does_not_equal": "Done"}
            },
        )
        if not results["results"]:
            return "No pending tasks. 🎉"

        lines = []
        for page in results["results"]:
            name_prop = page["properties"].get("Name", {}).get("title", [])
            title = name_prop[0]["text"]["content"] if name_prop else "Untitled"
            status_prop = page["properties"].get("Status", {}).get("select")
            status = status_prop["name"] if status_prop else "Unknown"
            due_prop = page["properties"].get("Due Date", {}).get("date")
            due = f" — due {due_prop['start']}" if due_prop else ""
            lines.append(f"• {title} [{status}]{due}")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch tasks: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. NOTION — CALENDAR
# ─────────────────────────────────────────────────────────────────────────────

@tool
def create_event(title: str, date: str, description: str = "") -> str:
    """
    Create a calendar event in your Notion calendar database.
    title: event name
    date: event date in YYYY-MM-DD format (e.g. 2025-12-25)
    description: optional details about the event
    """
    if not notion or not config.NOTION_CALENDAR_DB_ID:
        return "Notion calendar not configured. Add NOTION_CALENDAR_DB_ID to .env"
    try:
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Date": {"date": {"start": date}},
        }
        if description:
            properties["Description"] = {
                "rich_text": [{"type": "text", "text": {"content": description}}]
            }
        notion.pages.create(
            parent={"database_id": config.NOTION_CALENDAR_DB_ID},
            properties=properties,
        )
        return f"✅ Event '{title}' on {date} added to calendar."
    except Exception as e:
        return f"Failed to create event: {str(e)}"


@tool
def get_events(start_date: str = "", end_date: str = "") -> str:
    """
    Get upcoming calendar events from your Notion calendar.
    start_date: optional filter — show events on or after this date (YYYY-MM-DD)
    end_date: optional filter — show events on or before this date (YYYY-MM-DD)
    Leave both empty to get all events.
    """
    if not notion or not config.NOTION_CALENDAR_DB_ID:
        return "Notion calendar not configured."
    try:
        filters = []
        if start_date:
            filters.append({"property": "Date", "date": {"on_or_after": start_date}})
        if end_date:
            filters.append({"property": "Date", "date": {"on_or_before": end_date}})

        query = {"database_id": config.NOTION_CALENDAR_DB_ID}
        if len(filters) == 1:
            query["filter"] = filters[0]
        elif len(filters) > 1:
            query["filter"] = {"and": filters}

        results = notion.databases.query(**query)
        if not results["results"]:
            return "No events found."

        lines = []
        for page in results["results"]:
            name_prop = page["properties"].get("Name", {}).get("title", [])
            title = name_prop[0]["text"]["content"] if name_prop else "Untitled"
            date_prop = page["properties"].get("Date", {}).get("date")
            date = date_prop["start"] if date_prop else "No date"
            lines.append(f"• {title} — {date}")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch events: {str(e)}"

