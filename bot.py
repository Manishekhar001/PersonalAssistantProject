"""
Telegram bot — entry point of the entire application.

Uses python-telegram-bot in polling mode.
No domain or HTTPS needed. Just run this script and the bot starts.

Flow:
  Telegram user sends message
    → handle_message() is triggered
    → message is passed to the LangGraph agent
    → agent responds (possibly using tools)
    → response is sent back to Telegram
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)
from langchain_core.messages import HumanMessage

import config
from config import validate_config
from agent.graph import assistant
from agent.tools import init_db, get_weather, get_tasks, get_events

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /start command."""
    await update.message.reply_text(
        "👋 Hey! I'm your personal assistant.\n\n"
        "I can help you with:\n"
        "• General questions & web search\n"
        "• Reading and sending Gmail\n"
        "• Creating notes, tasks, and calendar events in Notion\n"
        "• Tracking your expenses\n\n"
        "Just type anything!"
    )


async def morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /morning command with weather, today's events, and pending tasks."""
    from datetime import datetime

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        # Fetch data directly from tools
        weather = await asyncio.to_thread(get_weather, "Hyderabad")
        tasks = await asyncio.to_thread(get_tasks)

        today = datetime.now().strftime("%Y-%m-%d")
        events = await asyncio.to_thread(get_events, today, today)

        # Format the response
        lines = ["Good morning! Here's your day:\n"]
        lines.append(f"🌤️ Weather: {weather}\n")
        lines.append("📅 Today's events:")
        lines.append(events if events and not events.startswith("Notion calendar not configured") else "No events for today.")
        lines.append("\n✅ Pending tasks:")
        lines.append(tasks if tasks and not tasks.startswith("Notion tasks not configured") else "No pending tasks. 🎉")

        response = "\n".join(lines)

    except Exception as e:
        logger.error(f"Morning command error: {e}", exc_info=True)
        response = "⚠️ Couldn't fetch your morning briefing. Please try again."

    await update.message.reply_text(response)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main message handler.
    Every text message from the user comes here.
    """
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name or "there"
    user_message = update.message.text

    logger.info(f"[User {user_id}] {user_message[:80]}")

    # Show "typing..." indicator while processing
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        # Run the synchronous agent in a thread so we don't block the async bot
        result = await asyncio.to_thread(
            assistant.invoke,
            {"messages": [HumanMessage(content=user_message)]},
            {"configurable": {"thread_id": user_id}},
        )

        # The last message in the result is always the assistant's reply
        response = result["messages"][-1].content

    except Exception as e:
        logger.error(f"Agent error for user {user_id}: {e}", exc_info=True)
        response = (
            "⚠️ Something went wrong on my end. Please try again.\n"
            f"Error: {str(e)}"
        )

    # Telegram has a 4096 character limit per message
    if len(response) > 4096:
        response = response[:4090] + "\n…"

    await update.message.reply_text(response)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log any unhandled errors from the Telegram library."""
    logger.error(f"Telegram error: {context.error}", exc_info=context.error)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Validate all required env vars before starting
    validate_config()

    # Set up the local SQLite database
    init_db()

    logger.info("Starting personal assistant bot...")

    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("morning", morning))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
