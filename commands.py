import logging
import html
import asyncio  # <-- Make sure this is imported
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import add_to_blacklist, remove_from_blacklist, get_blacklist
import config

# Set up logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---

# --- (NEW FUNCTION) ---
async def delete_and_reply(update: Update, text: str, parse_mode: str = None):
    """
    1. Deletes the user's triggering command.
    2. Sends a new reply from the bot.
    3. Deletes the bot's reply after 5 seconds.
    """
    
    # 1. Delete the user's command
    try:
        await update.message.delete()
    except Exception as e:
        # Bot might not have delete permissions
        logger.warning(f"Failed to delete user's command message: {e}")

    # 2. Send the bot's reply
    try:
        sent_message = await update.message.reply_text(text=text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Failed to send reply message: {e}")
        return # Can't continue if we failed to send
    
    # 3. Wait 5 seconds
    await asyncio.sleep(5)
    
    # 4. Delete the bot's reply
    try:
        await sent_message.delete()
    except Exception as e:
        # Message might have been deleted by someone else
        logger.warning(f"Failed to auto-delete bot reply: {e}")

# --- (END OF NEW FUNCTION) ---


async def is_admin(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the user is an admin.
    """
    if user_id in config.ADMIN_IDS_SET:
        return True
    
    try:
        chat_admins = await context.bot.get_chat_administrators(chat_id)
        for admin in chat_admins:
            if admin.user.id == user_id:
                return True
    except Exception as e:
        logger.warning(f"Could not get chat admins for {chat_id}: {e}")
        
    return False

async def is_group_chat(update: Update) -> bool:
    """Checks if the command was used in a group or supergroup."""
    if update.message.chat.type in ['group', 'supergroup']:
        return True
    
    # --- (UPDATED) ---
    await delete_and_reply(update, "This command must be used in a group chat.")
    return False

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    # --- (UPDATED) ---
    start_message = (
        "Hello! I am your new moderation bot.\n"
        "I am ready to protect this group.\n\n"
        "If you are a group admin, you can use these commands *in this chat*:\n"
        "• `/addblacklist [term]` - Add a term to the ban list\n"
        "• `/removeblacklist [term]` - Remove a term\n"
        "• `/listblacklist` - See all banned terms"
    )
    await delete_and_reply(update, start_message)

async def add_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a term to this group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update):
        return
    if not await is_admin(user_id, chat_id, context):
        # --- (UPDATED) ---
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return

    if not context.args:
        # --- (UPDATED) ---
        await delete_and_reply(update, "Usage: /addblacklist [term]")
        return

    term = " ".join(context.args).lower()
    
    try:
        success = await asyncio.to_thread(add_to_blacklist, chat_id, term)
        
        if success:
            # --- (UPDATED) ---
            await delete_and_reply(update, f"✅ Added '<code>{html.escape(term)}</code>' to this group's blacklist.", parse_mode=ParseMode.HTML)
        else:
            # --- (UPDATED) ---
            await delete_and_reply(update, f"'<code>{html.escape(term)}</code>' is already on this group's blacklist.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in add_blacklist_command: {e}")
        # --- (UPDATED) ---
        await delete_and_reply(update, "An error occurred while adding the term.")

async def remove_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a term from this group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update):
        return
    if not await is_admin(user_id, chat_id, context):
        # --- (UPDATED) ---
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return

    if not context.args:
        # --- (UPDATED) ---
        await delete_and_reply(update, "Usage: /removeblacklist [term]")
        return

    term = " ".join(context.args).lower()
    
    try:
        success = await asyncio.to_thread(remove_from_blacklist, chat_id, term)
        
        if success:
            # --- (UPDATED) ---
            await delete_and_reply(update, f"✅ Removed '<code>{html.escape(term)}</code>' from this group's blacklist.", parse_mode=ParseMode.HTML)
        else:
            # --- (UPDATED) ---
            await delete_and_reply(update, f"'<code>{html.escape(term)}</code>' was not found on this group's blacklist.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in remove_blacklist_command: {e}")
        # --- (UPDATED) ---
        await delete_and_reply(update, "An error occurred while removing the term.")

async def list_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all terms on this group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update):
        return
    if not await is_admin(user_id, chat_id, context):
        # --- (UPDATED) ---
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return

    try:
        terms = await asyncio.to_thread(get_blacklist, chat_id)
        
        if not terms:
            # --- (UPDATED) ---
            await delete_and_reply(update, "This group's blacklist is currently empty.")
            return

        message = "<b>Current Blacklisted Terms for this Group:</b>\n\n"
        for term in terms:
            escaped_term = html.escape(str(term)) 
            message += f"• <code>{escaped_term}</code>\n"

        # --- (UPDATED) ---
        await delete_and_reply(update, message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in list_blacklist_command: {e}")
        # --- (UPDATED) ---
        await delete_and_reply(update, "An error occurred while fetching the blacklist.")
