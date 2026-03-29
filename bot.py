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

  Telegram user sends a voice message
    → handle_voice() downloads and transcribes it via Groq Whisper
    → transcribed text is passed to the same agent pipeline

  /morning command → weather + events + tasks combined briefing
  /news command    → triggers the daily news emailer immediately (for testing)
"""

import asyncio
import datetime
import logging
import os

import pytz
from groq import Groq
from pydub import AudioSegment
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from langchain_core.messages import HumanMessage

import config
from config import validate_config
from agent.graph import assistant
from agent.tools import init_db, get_weather, get_tasks, get_events
from jobs.news_emailer import run_daily_news

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Groq client (for Whisper transcription) ───────────────────────────────────

_groq = Groq(api_key=config.GROQ_API_KEY)

IST = pytz.timezone("Asia/Kolkata")


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /start command."""
    await update.message.reply_text(
        "👋 Hey! I'm your personal assistant.\n\n"
        "I can help you with:\n"
        "• General questions & web search\n"
        "• Reading and sending Gmail\n"
        "• Summarising any URL\n"
        "• Creating notes, tasks, and calendar events in Notion\n"
        "• Tracking your expenses\n"
        "• Voice messages (just send one!)\n\n"
        "Commands:\n"
        "  /morning — daily briefing (weather + events + tasks)\n"
        "  /news    — send today's tech briefing emails now\n\n"
        "Just type or speak anything!"
    )


async def morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /morning command with weather, today's events, and pending tasks."""
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        weather = await asyncio.to_thread(get_weather, "Hyderabad")
        tasks = await asyncio.to_thread(get_tasks)

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        events = await asyncio.to_thread(get_events, today, today)

        def _clean(val: str, fallback: str) -> str:
            """Return fallback if val is empty or a 'not configured' message."""
            if not val or "not configured" in val.lower():
                return fallback
            return val

        weather_line = _clean(weather, "Unable to fetch weather right now.")
        events_line = _clean(events, "No events for today.")
        tasks_line = _clean(tasks, "No pending tasks. 🎉")

        response = (
            "Good morning! Here's your day:\n\n"
            f"🌤️ Weather: {weather_line}\n\n"
            f"📅 Today's events:\n{events_line}\n\n"
            f"✅ Pending tasks:\n{tasks_line}"
        )

    except Exception as e:
        logger.error(f"Morning command error: {e}", exc_info=True)
        response = "⚠️ Couldn't fetch your morning briefing. Please try again."

    await update.message.reply_text(response)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /news command — triggers the daily news emailer immediately."""
    await update.message.reply_text(
        "📰 Starting daily news research… this takes a few minutes.\n"
        "I'll email each sector briefing and confirm when done."
    )
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )
    try:
        # run_daily_news is synchronous — run in a thread to avoid blocking
        # Pass None for bot/chat_id here; the "done" confirmation is sent
        # directly below instead, avoiding cross-thread async complications.
        await asyncio.to_thread(run_daily_news)
        await update.message.reply_text("📬 Done! Check your inbox for all 6 briefings.")
    except Exception as e:
        logger.error(f"/news command error: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ News job encountered an error: {str(e)[:200]}"
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Download a Telegram voice note, transcribe via Groq Whisper, then pass
    the text through the same agent pipeline as a normal text message.
    """
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    tmp_dir = "data/tmp"
    os.makedirs(tmp_dir, exist_ok=True)

    ogg_path = os.path.join(tmp_dir, f"voice_{update.update_id}.ogg")
    wav_path = os.path.join(tmp_dir, f"voice_{update.update_id}.wav")

    try:
        # 1. Download .ogg from Telegram
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        await voice_file.download_to_drive(ogg_path)

        # 2. Convert .ogg → .wav using pydub + ffmpeg
        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")

        # 3. Transcribe with Groq Whisper
        with open(wav_path, "rb") as audio_file:
            transcription = _groq.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text",
            )

        # Groq returns a plain string when response_format="text"
        transcribed_text = (
            transcription.strip()
            if isinstance(transcription, str)
            else transcription.text.strip()
        )

        if not transcribed_text:
            await update.message.reply_text(
                "🎤 I couldn't make out what you said. Please try again."
            )
            return

        logger.info(
            f"Voice transcribed [{update.effective_user.id}]: {transcribed_text[:80]}"
        )

        # Echo so the user knows what was understood
        await update.message.reply_text(
            f"🎤 I heard: _{transcribed_text}_", parse_mode="Markdown"
        )

        # 4. Pass transcribed text through the agent (same path as text messages)
        user_id = str(update.effective_user.id)
        result = await asyncio.to_thread(
            assistant.invoke,
            {"messages": [HumanMessage(content=transcribed_text)]},
            {"configurable": {"thread_id": user_id}},
        )
        response = result["messages"][-1].content

    except Exception as e:
        logger.error(f"Voice handler error: {e}", exc_info=True)
        response = f"⚠️ Could not process your voice message: {str(e)[:200]}"

    finally:
        # 5. Clean up temp files regardless of success or failure
        for path in (ogg_path, wav_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    if len(response) > 4096:
        response = response[:4090] + "\n…"

    await update.message.reply_text(response)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler — every text message from the user comes here."""
    user_id = str(update.effective_user.id)
    user_message = update.message.text

    logger.info(f"[User {user_id}] {user_message[:80]}")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    try:
        result = await asyncio.to_thread(
            assistant.invoke,
            {"messages": [HumanMessage(content=user_message)]},
            {"configurable": {"thread_id": user_id}},
        )
        response = result["messages"][-1].content

    except Exception as e:
        logger.error(f"Agent error for user {user_id}: {e}", exc_info=True)
        response = (
            "⚠️ Something went wrong on my end. Please try again.\n"
            f"Error: {str(e)}"
        )

    if len(response) > 4096:
        response = response[:4090] + "\n…"

    await update.message.reply_text(response)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log any unhandled errors from the Telegram library."""
    logger.error(f"Telegram error: {context.error}", exc_info=context.error)


# ── Scheduled job callbacks (must be async for python-telegram-bot v20+) ─────

async def _daily_news_job(context: CallbackContext) -> None:
    """Scheduled job: fetch and email the daily tech briefing at 07:00 IST."""
    chat_id = config.MY_TELEGRAM_CHAT_ID
    try:
        await asyncio.to_thread(run_daily_news)
        if chat_id:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text="📬 Daily briefing sent — 6 emails delivered to your inbox.",
            )
    except Exception as e:
        logger.error(f"Daily news job failed: {e}", exc_info=True)
        if chat_id:
            try:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=f"⚠️ Daily news job failed: {str(e)[:200]}",
                )
            except Exception:
                pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    """Build and start the Telegram bot application."""
    validate_config()
    init_db()

    logger.info("Starting personal assistant bot...")

    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # ── Command handlers ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("morning", morning))
    app.add_handler(CommandHandler("news", news_command))

    # ── Message handlers ──────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ── Scheduled job: daily news at 07:00 IST ────────────────────────────────
    if config.MY_TELEGRAM_CHAT_ID:
        app.job_queue.run_daily(
            callback=_daily_news_job,
            time=datetime.time(hour=7, minute=0, tzinfo=IST),
            name="daily_news",
        )
        logger.info("Daily news job scheduled at 07:00 IST.")
    else:
        logger.warning(
            "MY_TELEGRAM_CHAT_ID not set — daily news job will not be scheduled. "
            "Use /news to trigger manually."
        )

    app.add_error_handler(error_handler)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
