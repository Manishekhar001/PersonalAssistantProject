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
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from groq import Groq
from langchain_core.tools import tool
from serpapi import GoogleSearch
from notion_client import Client

import config

# ── Notion client (shared across Notion tools) ────────────────────────────────
notion = Client(auth=config.NOTION_API_KEY) if config.NOTION_API_KEY else None

# ── Groq client (used directly for summarize_url) ─────────────────────────────
_groq = Groq(api_key=config.GROQ_API_KEY)


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
# 3. URL SUMMARIZER
# ─────────────────────────────────────────────────────────────────────────────

@tool
def summarize_url(url: str) -> str:
    """
    Fetch a webpage and summarize its main content in 5 bullet points.
    url: the full URL of the webpage to summarize (must start with http)
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove boilerplate tags
        for tag in soup(["nav", "footer", "header", "aside", "script", "style",
                          "noscript", "form", "button", "iframe", "figure"]):
            tag.decompose()

        # Prefer <article> or <main>, fall back to <body>
        content_node = soup.find("article") or soup.find("main") or soup.body
        if not content_node:
            return "Could not extract content from this page."

        raw_text = content_node.get_text(separator="\n", strip=True)

        # Trim to ~6000 characters to stay within token limits
        raw_text = raw_text[:6000]

        if not raw_text.strip():
            return "The page appears to have no readable text content."

        response = _groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=512,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise research assistant. "
                        "Given article text, return EXACTLY 5 bullet points summarising the key information. "
                        "Each bullet starts with '• '. No preamble, no extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Summarize this article in 5 bullet points:\n\n{raw_text}",
                },
            ],
        )

        return response.choices[0].message.content.strip()

    except requests.exceptions.RequestException as e:
        return f"Could not fetch the URL: {str(e)}"
    except Exception as e:
        return f"summarize_url failed: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. GMAIL — READ
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
# 5. GMAIL — SEND
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
# 6. NOTION — NOTES
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
# 7. NOTION — TASKS
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
# 8. NOTION — CALENDAR
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


# ─────────────────────────────────────────────────────────────────────────────
# 9. REMINDERS (SQLite — local)
# ─────────────────────────────────────────────────────────────────────────────

@tool
def set_reminder(user_id: str, message: str, minutes: int) -> str:
    """
    Set a reminder that will be sent after X minutes.
    user_id: the user's Telegram ID (thread_id)
    message: what to remind the user about
    minutes: how many minutes from now to send the reminder (min 1, max 1440)
    """
    try:
        minutes = max(1, min(int(minutes), 1440))  # Clamp between 1 and 24 hours
        remind_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO reminders (user_id, message, remind_at) VALUES (?, ?, ?)",
            (user_id, message, remind_at),
        )
        conn.commit()
        conn.close()

        return f"⏰ Reminder set! I'll remind you in {minutes} minute{'s' if minutes > 1 else ''}: '{message}'"
    except Exception as e:
        return f"Failed to set reminder: {str(e)}"


def get_pending_reminders() -> list:
    """Get all unsent reminders that are due. Called by bot.py on startup and by the job."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT id, user_id, message, remind_at FROM reminders WHERE sent = 0 AND remind_at <= ?",
            (now,),
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def mark_reminder_sent(reminder_id: int) -> None:
    """Mark a reminder as sent so it doesn't trigger again."""
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 10. EXPENSES (SQLite — local)
# ─────────────────────────────────────────────────────────────────────────────


@tool
def add_expense(amount: float, category: str, description: str = "") -> str:
    """
    Add an expense entry to the local database.
    amount: amount in rupees (e.g. 250.0)
    category: expense category (e.g. Food, Transport, Shopping)
    description: optional short note
    """
    try:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "INSERT INTO expenses (date, category, amount, description) VALUES (?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d"), category, amount, description),
        )
        conn.commit()
        conn.close()
        return f"✅ ₹{amount:.2f} added under '{category}'."
    except Exception as e:
        return f"Failed to add expense: {str(e)}"


@tool
def get_expenses(limit: int = 10) -> str:
    """
    Get recent expense entries from the local database.
    limit: how many recent entries to show (default 10)
    """
    try:
        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute(
            "SELECT date, category, amount, description FROM expenses ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        total = conn.execute("SELECT SUM(amount) FROM expenses").fetchone()[0] or 0
        conn.close()

        if not rows:
            return "No expenses recorded yet."

        lines = [f"• {r[0]} | {r[1]} | ₹{r[2]:.2f} | {r[3]}" for r in rows]
        lines.append(f"\n📊 All-time total: ₹{total:.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch expenses: {str(e)}"


def init_db():
    """Create the expenses and reminders tables. Called once at startup."""
    import os
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/tmp", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            description TEXT    DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            remind_at   TEXT    NOT NULL,
            sent        INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
