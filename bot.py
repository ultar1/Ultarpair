import logging
import os
import asyncio
from threading import Thread
from flask import Flask
from telegram.ext import (
    Application,
    CommandHandler,
    ChatMemberHandler,
)

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

# --- Health Check Web Server (Unchanged) ---
app = Flask(__name__)
@app.route('/')
def health_check():
    """Responds to Render's health check."""
    return "Bot is alive!", 200

def run_web_server():
    """Runs the Flask web server."""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
# --- End of Web Server Code ---


def main():
    """Start the bot and the web server."""
    
    # 1. Check for essential environment variables
    if not config.TOKEN:
        logger.critical("!!! ERROR: BOT_TOKEN environment variable not set. !!!")
        return
        
    if not config.DATABASE_URL:
        logger.critical("!!! ERROR: DATABASE_URL environment variable not set. !!!")
        return

    # 2. Initialize the database
    try:
        init_db()
        logger.info("Database connection established and tables checked.")
    except Exception as e:
        logger.critical(f"!!! CRITICAL: Could not connect to database. {e} !!!")
        return

    # 3. Start the health check web server in a background thread
    logger.info("Starting health check web server...")
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("Web server started.")

    # 4. --- THIS IS THE FIX ---
    # Use Application.builder() instead of Updater()
    logger.info("Building Telegram application...")
    application = Application.builder().token(config.TOKEN).build()
    logger.info("Application built.")

    # 5. Get the dispatcher to register handlers (now from 'application')
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    application.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    application.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    application.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    # 6. Start the Bot
    # This call is now 'run_polling()' and it's blocking,
    # which is fine since the web server is in another thread.
    logger.info("Bot started and polling...")
    application.run_polling()

if __name__ == '__main__':
    main()
