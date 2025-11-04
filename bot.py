import logging
import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
)
from telegram.constants import UpdateType # To specify update types

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

# --- NEW: Async Health Check ---
async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    A simple async HTTP endpoint for Render's health check.
    This is NOT a Telegram command.
    """
    # This is a special object injected by the library for HTTP routes
    if update.effective_user: 
        return
        
    await update.effective_message.reply_text("Bot is alive and listening!", quote=False)


# --- NEW: Bot Setup Function ---
def create_application() -> Application:
    """Creates and configures the Telegram Application."""
    
    # 1. Initialize DB (This is sync, run it first)
    logger.info("Initializing database...")
    init_db()

    # 2. Build the application
    try:
        builder = Application.builder().token(config.TOKEN)
        
        # 3. (FIX) Set webhook settings *during build*
        webhook_url = f"{config.WEBHOOK_URL}/webhook"
        
        # --- Webhook secret token has been removed ---
        builder.webhook(
            url=webhook_url,
            allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER]
        )
        
        application = builder.build()
        logger.info("Telegram Application built successfully.")

    except Exception as e:
        logger.critical(f"Failed to build Telegram Application: {e}", exc_info=True)
        exit(1)

    # 4. Register all your handlers
    logger.info("Registering handlers...")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(CommandHandler("silent", silent_command))
    application.add_handler(CommandHandler("pin", pin_command))
    application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    # 5. (FIX) Add the health check as an HTTP route
    # This tells PTB to answer GET requests on "/"
    application.add_route_handler("/", health_check)
    
    # --- The secret token check handler has been removed ---

    logger.info("Application setup complete.")
    return application

# --- Create the app for Gunicorn ---
# This block runs when Gunicorn imports the file
if __name__ != "__main__":
    # --- Removed WEBHOOK_SECRET from this check ---
    if not all([config.TOKEN, config.DATABASE_URL, config.WEBHOOK_URL]):
        logger.critical("!!! ERROR: Missing TOKEN, DATABASE_URL, or WEBHOOK_URL. !!!")
        exit(1)
    else:
        logger.info("All environment variables seem to be set.")
        application = create_application()
        logger.info("ASGI application created. Ready for Gunicorn.")
