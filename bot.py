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
from asgiref.wsgi import WsgiToAsgi # <--- Translator

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
logger = logging.getLogger(__name__)

# --- Initialize Flask App and Telegram Application ---
flask_app = Flask(__name__) # <--- Renamed to 'flask_app'

# Build the Telegram Application
# We build it here so both our setup and webhook handler can use it
try:
    application = Application.builder().token(config.TOKEN).build()
    logger.info("Telegram Application built successfully.")
except Exception as e:
    logger.critical(f"Failed to build Telegram Application: {e}")
    # If we can't build the app, nothing else will work
    exit(1)


# --- Bot Setup ---
async def setup_bot():
    """Initializes DB, sets handlers, and sets the webhook."""
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Registering handlers...")
    # Register all your command and member handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Tell Telegram where to send updates (our webhook URL)
    try:
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        logger.info(f"Setting webhook to: {webhook_url}")
        
        # We have removed the secret_token from this call
        await application.bot.set_webhook(
            url=webhook_url
        )
        logger.info("Webhook set successfully.")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")

# --- Web Server Routes ---

@flask_app.route('/')
def health_check():
    """Responds to Render's health check."""
    return "Bot is alive and listening for webhooks!", 200

@flask_app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    """Handles incoming updates from Telegram."""
    
    # 1. We have removed the secret token check.
        
    try:
        # 2. Get the JSON data from Telegram
        # THIS IS THE CORRECTED LINE
        data = request.get_json()
        
        # 3. Create an Update object
        update = Update.de_json(data, application.bot)
        
        # 4. Process the update (this runs your command/moderation handlers)
        await application.process_update(update)
        
        return "ok", 200
        
    except Exception as e:
        # We log the *actual* error, not the 'await' error
        logger.error(f"Error handling webhook: {e}")
        return "error", 500

# --- Setup on Gunicorn Start ---

# Check for required env vars *before* trying to run setup
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
        asyncio.run(setup_bot())
        logger.info("Async setup complete. Ready for Gunicorn.")
    except Exception as e:
        logger.critical(f"Failed to run async setup: {e}")

# 4. WRAP THE APP
# This is the translator that fixes the server crash.
app = WsgiToAsgi(flask_app)

# DO NOT ADD app.run() or if __name__ == '__main__':
# Gunicorn will manage the server.
