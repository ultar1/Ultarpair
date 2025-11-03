import logging
import os
from threading import Thread
from flask import Flask
from telegram.ext import (
    Updater,
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

# --- NEW: Health Check Web Server ---
# Render's Web Service needs a port to bind to.
# This simple Flask app runs in a thread to respond to health checks.

app = Flask(__name__)
@app.route('/')
def health_check():
    """Responds to Render's health check."""
    return "Bot is alive!", 200

def run_web_server():
    """Runs the Flask web server."""
    # Get the port from Render's environment variable
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

    # 3. --- NEW: Start the health check web server in a background thread ---
    logger.info("Starting health check web server...")
    # The `daemon=True` flag means this thread will stop when the main script stops
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info("Web server started.")

    # 4. Create the Updater and pass it your bot's token.
    updater = Updater(config.TOKEN)

    # 5. Get the dispatcher to register handlers
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    dispatcher.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    dispatcher.add_handler(CommandHandler("listblacklist", list_blacklist_command))
    dispatcher.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    # 6. Start the Bot
    updater.start_polling()
    logger.info("Bot started and polling...")

    # 7. Run the bot until you press Ctrl-C
    # The script will now idle here, while the web server runs in its thread.
    updater.idle()

if __name__ == '__main__':
    main()
