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
    silent_command,
    pin_command,
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

# --- (NEW) Async-only setup ---
async def setup_bot_async():
    """Run the async part of the setup."""
    logger.info("Initializing Telegram Application...")
    await application.initialize()
    
    logger.info("Setting webhook...")
    try:
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER]
        )
        logger.info(f"Webhook set successfully to: {webhook_url}")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")

# --- Web Server Routes ---
@flask_app.route('/')
def health_check():
    """Responds to Render's health check."""
    return "Bot is alive and listening for webhooks!", 200

@flask_app.route('/webhook', methods=['POST'])
def telegram_webhook(): # <-- This MUST be sync (it's a Flask route)
    """Handles incoming updates from Telegram."""
    try:
        data = request.get_json()
        update = Update.de_json(data, application.bot)
        
        # --- (THIS IS THE FIX) ---
        # Get the same event loop Gunicorn/Uvicorn is running on
        loop = asyncio.get_event_loop()
        
        # Use run_coroutine_threadsafe to schedule the async task
        # on that loop. This is thread-safe and non-blocking.
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        
        return "ok", 200
        
    except Exception as e:
        # Log the *actual* error
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        return "error", 500

# --- Setup on Gunicorn Start ---
# This block runs when Gunicorn imports the file
if __name__ != "__main__":
    if not config.TOKEN:
        logger.critical("!!! ERROR: BOT_TOKEN is not set. !!!")
    elif not config.DATABASE_URL:
        logger.critical("!!! ERROR: DATABASE_URL is not set. !!!")
    elif not config.WEBHOOK_URL:
        logger.critical("!!! ERROR: WEBHOOK_URL is not set. !!!")
    else:
        logger.info("All environment variables seem to be set.")
        
        # 1. Run SYNC setup
        logger.info("Initializing database...")
        init_db()
        
        logger.info("Registering handlers...")
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
        application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
        application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
        application.add_handler(CommandHandler("silent", silent_command)) # <-- ADD THIS
        application.add_handler(CommandHandler("pin", pin_command))       # <-- ADD THIS
        application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

        # 2. Get the main event loop
        try:
            loop = asyncio.get_event_loop()
            logger.info("Got main event loop.")
            
            # 3. Run ASYNC setup on that loop
            logger.info("Running async setup (initialize, set_webhook)...")
            loop.run_until_complete(setup_bot_async())
            logger.info("Async setup complete.")
            
        except Exception as e:
            logger.critical(f"Failed to run async setup: {e}", exc_info=True)
            # Don't create the app if setup failed
            exit(1)

        # 4. Create the ASGI app *after* setup is complete
        app = WsgiToAsgi(flask_app)
        logger.info("ASGI app created. Ready for Gunicorn.")
