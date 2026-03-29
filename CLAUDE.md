# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Telegram-based personal assistant bot built with Python, LangGraph, and Groq LLM. The agent can perform web searches, manage Gmail, create Notion notes/tasks/calendar events, and track expenses in a local SQLite database.

## Architecture

```
User (Telegram)
    ↓
bot.py — Telegram bot polling (async)
    ↓
agent/graph.py — LangGraph ReAct agent (sync, wrapped with asyncio.to_thread)
    ↓
agent/tools.py — 11 tools across 5 categories:
    • Web: SerpAPI (web_search)
    • Gmail: IMAP + SMTP (read_emails, send_email)
    • Notion: Notes, Tasks, Calendar (create/get operations)
    • Local: SQLite (add_expense, get_expenses)
```

**Memory**: Uses LangGraph's `MemorySaver` with `thread_id` set to the user's Telegram ID for per-user conversation history (in-memory only, lost on restart).

**Agent**: ReAct agent via `langgraph.prebuilt.create_react_agent` using Groq's `llama-3.3-70b-versatile` model with temperature=0.

## Environment Setup

Copy `.env.example` to `.env` and fill in required keys:
- `GROQ_API_KEY` — from console.groq.com
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `SERPAPI_API_KEY` — from serpapi.com
- `NOTION_API_KEY`, `NOTION_NOTES_PAGE_ID`, `NOTION_TASKS_DB_ID`, `NOTION_CALENDAR_DB_ID` — from notion.so/my-integrations
- `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` — App Password from myaccount.google.com/apppasswords (requires 2FA)

## Common Commands

**Local development** (Python 3.11+ required):
```bash
# Create venv and install dependencies
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the bot locally
python bot.py
```

**EC2 deployment** (see README.md for full EC2 setup):
```bash
# Run setup script (creates systemd service)
bash deploy/setup.sh

# Start/stop/restart the service
sudo systemctl start personal-assistant
sudo systemctl stop personal-assistant
sudo systemctl restart personal-assistant

# View logs
sudo journalctl -u personal-assistant -f
sudo journalctl -u personal-assistant --since "1 hour ago"
```

## Key Files

- `bot.py` — Entry point. Telegram bot setup, message handlers, error handling. Runs agent calls via `asyncio.to_thread()` to avoid blocking the async event loop.
- `agent/graph.py` — Agent factory. Creates the ReAct agent with system prompt, tools, and memory checkpointer.
- `agent/tools.py` — All 11 tool implementations. Shared Notion client, SQLite init function.
- `config.py` — Environment variable loader with `validate_config()` for startup checks.
- `deploy/setup.sh` — EC2 Ubuntu setup script. Installs Python 3.11, creates venv, installs deps, sets up systemd service.
- `data/expenses.db` — Auto-created SQLite database for expense tracking.

## Adding New Tools

1. Define the tool function in `agent/tools.py` with the `@tool` decorator
2. Import it in `agent/graph.py` and add to the `tools` list in `create_assistant()`
3. Update the `SYSTEM_PROMPT` in `agent/graph.py` to mention the new capability
4. For external APIs: add config to `config.py` and `.env.example`

## Testing

No formal test suite exists. Manual testing via Telegram:
- `/start` — Welcome message
- General Q&A (direct LLM)
- "What's the weather in Hyderabad?" → triggers web_search
- "Add expense 150 food lunch" → triggers add_expense
- "Show my expenses" → triggers get_expenses
- "Create a task: Review report, due 2025-12-31" → triggers create_task
- "What are my pending tasks?" → triggers get_tasks
- "Create note titled X: content" → triggers create_note
- "Schedule event: Team call on 2025-12-20" → triggers create_event
- "Read my emails" → triggers read_emails
- "Send email to someone@example.com about subject" → triggers send_email

## Dependencies

Core: `python-telegram-bot`, `langchain-groq`, `langchain`, `langgraph`, `notion-client`, `google-search-results`, `python-dotenv`

No dev dependencies — linting/testing not configured.
