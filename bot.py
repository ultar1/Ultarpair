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

# Import httpx for the self-ping loop
import httpx # <-- Make sure this is installed!

# Import handlers
from commands import (
    start_command,
    add_blacklist_command,
    remove_blacklist_command,
    silent_command,
    antibot_command,
    pin_command,
    ban_command,
    kick_command,
    invite_command,
    antilink_command,
    antiword_command,
    list_blacklist_command,
    welcome_command,     
    setwelcome_command       
)
from moderation import check_new_member, handle_message

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Build the Telegram Application
try:
    application = Application.builder().token(config.TOKEN).build()
    logger.info("Telegram Application built successfully.")
except Exception as e:
    logger.critical(f"Failed to build Telegram Application: {e}", exc_info=True)
    exit(1)


# --- NEW: Simple HTTP Health Check Handler ---
# This handler is hit by the self-ping loop to keep the app awake.
async def health_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /health endpoint for cron jobs and self-ping."""
    # Only reply if it's an internal HTTP call (no effective user) and the command is /health
    if not update.effective_user and update.message and update.message.text == "/health":
        await update.message.reply_text("ok", quote=False)


# --- Bot Setup ---
async def setup_bot():
    """Initializes DB and registers handlers."""
    
    logger.info("Initializing database...")
    await asyncio.to_thread(init_db)
    
    logger.info("Registering handlers...")
    
    # Command Handlers (group 0)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(CommandHandler("silent", silent_command))
    application.add_handler(CommandHandler("pin", pin_command))
    application.add_handler(CommandHandler("antilink", antilink_command))
    application.add_handler(CommandHandler("antiword", antiword_command))
    application.add_handler(CommandHandler("kick", kick_command)) 
    application.add_handler(CommandHandler("ban", ban_command)) 
    application.add_handler(CommandHandler("invite", invite_command)) 
    application.add_handler(CommandHandler("antibot", antibot_command)) 
    application.add_handler(CommandHandler("welcome", welcome_command))     
    application.add_handler(CommandHandler("setwelcome", setwelcome_command))   
    
    # --- FIX: Register the health check handler ---
    application.add_handler(CommandHandler("health", health_check_handler))
    # --- END FIX ---

    # Chat Member Handler (group 0)
    application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Message Handler (group 1 - runs after commands)
    application.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND) & (filters.ChatType.GROUPS), 
        handle_message
    ), group=1)

    logger.info("Initializing Telegram Application...")
    await application.initialize()
    logger.info("Handlers and DB are set up.")

# --- Self-Ping Loop ---
async def ping_self_loop():
    """Pings a service every 6 minutes to prevent the app from spinning down."""
    PING_INTERVAL = 6 * 60 
    
    # PING the dedicated /webhook?message=/health endpoint
    ping_url = f"{config.WEBHOOK_URL}/webhook?message=/health"

    logger.info("Self-ping worker started.")
    await asyncio.sleep(5) 

    while True:
        try:
            logger.info(f"Pinging self at {ping_url} to stay alive...")
            async with httpx.AsyncClient(timeout=10) as client:
                # Use a POST request to hit the webhook endpoint
                response = await client.post(ping_url) 
                # We expect status 200/202 from the webhook server
                logger.info(f"Self-ping successful. Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Self-ping FAILED: {e}")
            
        await asyncio.sleep(PING_INTERVAL)


# --- Main function to start the bot ---
async def main():
    """Set up and run the bot's webhook server."""
    
    await setup_bot() 

    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = f"{config.WEBHOOK_URL}/webhook"
    
    logger.info(f"Starting webhook server on 0.0.0.0:{PORT}")
    
    # 1. Start the webhook server 
    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook", 
        webhook_url=WEBHOOK_URL,
        allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER]
    )
    
    # 2. Start the self-ping task
    asyncio.create_task(ping_self_loop())
    
    # 3. Start the application logic
    await application.start()
    
    # 4. Wait forever until the process is stopped
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down (received signal)...")
    finally:
        # 5. Gracefully shut down when stopped
        logger.info("Stopping webhook...")
        await application.updater.stop()
        logger.info("Stopping application...")
        await application.stop()
        logger.info("Bot shut down complete.")


if __name__ == "__main__":
    if not all([config.TOKEN, config.DATABASE_URL, config.WEBHOOK_URL]):
        logger.critical("!!! ERROR: Missing TOKEN, DATABASE_URL, or WEBHOOK_URL. !!!")
        exit(1)
    
    # We must ensure httpx is installed for this worker to run correctly
    try:
        import httpx
    except ImportError:
        logger.critical("!!! ERROR: httpx library not found. Please add 'httpx' to your requirements.txt. !!!")
        exit(1)
        
    logger.info("Starting bot...")
    asyncio.run(main())
