import logging
import os
import asyncio
from flask import Flask, request, abort
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
)
from asgiref.wsgi import WsgiToAsgi # This is the translator

# Import config (which loads env vars) and database functions
import config
from database import init_db

# Import handlers
from commands import (
    start_command,
    add_blacklist_command,
    remove_blacklist_command,
    list_blacklist_command
)
from moderation import check_new_member

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
# Reduce httpx logging noise
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- Initialize Flask App and Telegram Application ---
flask_app = Flask(__name__) # Renamed to 'flask_app'

# Build the Telegram Application
try:
    application = Application.builder().token(config.TOKEN).build()
    logger.info("Telegram Application built successfully.")
except Exception as e:
    logger.critical(f"Failed to build Telegram Application: {e}")
    exit(1)


# --- Bot Setup ---
async def setup_bot():
    """Initializes DB, handlers, the application, and the webhook."""
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Registering handlers...")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Initializing Telegram Application...")
    await application.initialize()

    # Tell Telegram where to send updates (our webhook URL)
    try:
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        logger.info(f"Setting webhook to: {webhook_url}")
        
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER]
        )
        logger.info("Webhook set successfully with allowed_updates.")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")

# --- Web Server Routes ---

@flask_app.route('/')
def health_check():
    """Responds to Render's health check."""
    return "Bot is alive and listening for webhooks!", 200

# --- (THIS IS THE FIX) ---
@flask_app.route('/webhook', methods=['POST'])
def telegram_webhook(): # <-- 1. This is now SYNC (no 'async')
    """Handles incoming updates from Telegram."""
        
    try:
        # Get data synchronously
        data = request.get_json()
        
        # De-serialize update synchronously
        update = Update.de_json(data, application.bot)
        
        # 2. Hand off the async processing to the bot's event loop
        # This is thread-safe and runs in the background.
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            application.loop
        )
        
        # 3. Return "ok" to Telegram immediately
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return "error", 500
# --- (END OF FIX) ---


# --- Setup on Gunicorn Start ---
# This code runs ONCE when your Gunicorn worker starts.
if not config.TOKEN:
    logger.critical("!!! ERROR: BOT_TOKEN is not set. !!!")
elif not config.DATABASE_URL:
    logger.critical("!!! ERROR: DATABASE_URL is not set. !!!")
elif not config.WEBHOOK_URL:
    logger.critical("!!! ERROR: WEBHOOK_URL is not set. !!!")
else:
    logger.info("All environment variables seem to be set.")
    logger.info("Running async setup to set webhook...")
    try:
        # This runs our setup_bot() function
        asyncio.run(setup_bot())
        logger.info("Async setup complete. Ready for Gunicorn.")
    except Exception as e:
        logger.critical(f"Failed to run async setup: {e}")

# --- WRAP THE APP ---
# This line now makes perfect sense:
# We are wrapping our SYNC Flask app to run on an ASYNC Gunicorn/Uvicorn server
app = WsgiToAsgi(flask_app)
