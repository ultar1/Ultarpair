import logging
import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
    MessageHandler
)

# Import config (which loads env vars) and database functions
import config
from database import init_db

# Import handlers
from commands import (
    start_command,
    add_blacklist_command,
    remove_blacklist_command,
    silent_command,
   antibot_command,
    pin_command,
   antilink_command,
   antiword_command,
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

# Build the Telegram Application
try:
    application = Application.builder().token(config.TOKEN).build()
    logger.info("Telegram Application built successfully.")
except Exception as e:
    logger.critical(f"Failed to build Telegram Application: {e}", exc_info=True)
    exit(1)


# --- Bot Setup ---
async def setup_bot():
    """Initializes DB and registers handlers."""
    
    logger.info("Initializing database...")
    # Run sync init_db in a thread to be safe
    await asyncio.to_thread(init_db)
    
    logger.info("Registering handlers...")
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(CommandHandler("silent", silent_command))
    application.add_handler(CommandHandler("pin", pin_command))
    application.add_handler(CommandHandler("antilink", antilink_command))  # <-- NEW
     application.add_handler(CommandHandler("antiword", antiword_command))  # <-- NEW
    application.add_handler(CommandHandler("antibot", antibot_command)) 
    application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    logger.info("Initializing Telegram Application...")
    await application.initialize()
    logger.info("Handlers and DB are set up.")
    # We no longer call set_webhook here. The main() function will do it.


# --- Main function to start the bot ---
async def main():
    """Set up and run the bot's webhook server."""
    
    # Run the setup function
    await setup_bot() 

    # Get port from environment variables (for Render)
    # Default to 8443 if not set (for local testing)
    PORT = int(os.environ.get("PORT", 8443))
    
    # Get webhook URL from config
    WEBHOOK_URL = f"{config.WEBHOOK_URL}/webhook"
    
    logger.info(f"Starting webhook server on 0.0.0.0:{PORT}")
    
    # 1. Start the webhook server (this runs in the background)
    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook", # We just need the path here
        webhook_url=WEBHOOK_URL,
        allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER]
    )
    
    # 2. Start the application logic (processing updates)
    await application.start()
    
    # 3. Wait forever until the process is stopped (e.g., by Render)
    # This prevents the script from exiting.
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down (received signal)...")
    finally:
        # 4. Gracefully shut down when stopped
        logger.info("Stopping webhook...")
        await application.updater.stop()
        logger.info("Stopping application...")
        await application.stop()
        logger.info("Bot shut down complete.")


if __name__ == "__main__":
    # Check for essential env vars first
    if not all([config.TOKEN, config.DATABASE_URL, config.WEBHOOK_URL]):
        logger.critical("!!! ERROR: Missing TOKEN, DATABASE_URL, or WEBHOOK_URL. !!!")
        exit(1)
    
    logger.info("Starting bot...")
    # This creates the loop and runs our main function
    asyncio.run(main())

