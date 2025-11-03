import logging
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

def main():
    """Start the bot."""
    
    # 1. Check for essential environment variables
    if not config.TOKEN:
        logger.critical("!!! ERROR: BOT_TOKEN environment variable not set. !!!")
        return
        
    if not config.DATABASE_URL:
        logger.critical("!!! ERROR: DATABASE_URL environment variable not set. !!!")
        return

    # 2. Initialize the database (create tables if they don't exist)
    try:
        init_db()
        logger.info("Database connection established and tables checked.")
    except Exception as e:
        logger.critical(f"!!! CRITICAL: Could not connect to database. {e} !!!")
        return

    # 3. Create the Updater and pass it your bot's token.
    updater = Updater(config.TOKEN)

    # 4. Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # --- Register Command Handlers ---
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("addblacklist", add_blacklist_command))
    dispatcher.add_handler(CommandHandler("removeblacklist", remove_blacklist_command))
    dispatcher.add_handler(CommandHandler("listblacklist", list_blacklist_command))

    # --- Register New Member Handler ---
    dispatcher.add_handler(ChatMemberHandler(check_new_member, ChatMemberHandler.CHAT_MEMBER))

    # 5. Start the Bot
    updater.start_polling()
    logger.info("Bot started and polling...")

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()
