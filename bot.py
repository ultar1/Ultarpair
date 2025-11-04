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
    silent_command,       # <-- Added
    pin_command,          # <-- Added
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
    logger.critical(f"Failed to build Telegram Application: {e}", exc_info=True)
    exit(1)


# --- Bot Setup ---
async def setup_bot():
    """Initializes DB, handlers, the application, and the webhook."""
    # This runs inside the main loop, so we can use 'await'
    
    logger.info("Initializing database...")
    # Run sync init_db in a thread to be safe
    await asyncio.to_thread(init_db)
    
    logger.info("Registering handlers...")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(CommandHandler("silent", silent_command))    # <-- Added
    application.add_handler(CommandHandler("pin", pin_command))        # <-- Added
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
        logger.error(f"Error setting webhook: {e}", exc_info=True)

# --- Web Server Routes ---

@flask_app.route('/')
def health_check():
    """Responds to Render's health check."""
    return "Bot is alive and listening for webhooks!", 200

# --- (THIS IS THE FIRST FIX) ---
@flask_app.route('/webhook', methods=['POST'])
def telegram_webhook(): # <-- Must be SYNC for Flask
    """Handles incoming updates from Telegram."""
    try:
        data = request.get_json()
        update = Update.de_json(data, application.bot)
        
        # Get the event loop we saved at startup
        loop = flask_app.main_loop 
        
        # Safely schedule the async processing on that loop
        # This is non-blocking and thread-safe.
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            loop
        )
        
        return "ok", 200
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        return "error", 500

# --- (THIS IS THE SECOND FIX) ---
# --- Setup on Gunicorn Start ---
if __name__ != "__main__":
    if not all([config.TOKEN, config.DATABASE_URL, config.WEBHOOK_URL]):
        logger.critical("!!! ERROR: Missing TOKEN, DATABASE_URL, or WEBHOOK_URL. !!!")
        exit(1)
    else:
        logger.info("All environment variables seem to be set.")
        
        try:
            # 1. Get the main event loop from Gunicorn/Uvicorn
            loop = asyncio.get_event_loop()
            logger.info("Got main event loop.")
            
            # 2. Save it to the flask_app object
            # This is safe and fixes the "no attribute" error
            flask_app.main_loop = loop
            logger.info("Saved event loop to flask_app.main_loop.")

            # 3. Run your async setup ON THAT LOOP
            logger.info("Running async setup (db, handlers, webhook)...")
            loop.run_until_complete(setup_bot())
            logger.info("Async setup complete.")

        except Exception as e:
            logger.critical(f"Failed to run async setup: {e}", exc_info=True)
            exit(1)

        # 4. Create the ASGI app for Gunicorn to use
        app = WsgiToAsgi(flask_app)
        logger.info("ASGI app created. Ready for Gunicorn.")
