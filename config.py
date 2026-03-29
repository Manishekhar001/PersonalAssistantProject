import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MY_TELEGRAM_CHAT_ID = os.getenv("MY_TELEGRAM_CHAT_ID")  # Your personal chat ID for daily news delivery

# --- Web Search ---
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# --- News API ---
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")  # newsapi.org — 100 free requests/day

# --- Gmail ---
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# --- Notion ---
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_NOTES_PAGE_ID = os.getenv("NOTION_NOTES_PAGE_ID")   # Parent page for notes
NOTION_TASKS_DB_ID = os.getenv("NOTION_TASKS_DB_ID")       # Tasks database
NOTION_CALENDAR_DB_ID = os.getenv("NOTION_CALENDAR_DB_ID") # Calendar database

# --- Local DB ---
DB_PATH = "data/expenses.db"


def validate_config():
    """Check required keys are present on startup."""
    required = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "NOTION_API_KEY": NOTION_API_KEY,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
