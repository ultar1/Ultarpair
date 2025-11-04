import logging
import html
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import add_to_blacklist, remove_from_blacklist, get_blacklist
import config

# Set up logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---

async def is_admin(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the user is an admin.
    Admins are:
    1. Super Admins (from config.py)
    2. Admins or Creators of the chat.
    """
    
    # 1. Check if they are a Super Admin (fastest check)
    if user_id in config.ADMIN_IDS_SET:
        return True
    
    # 2. If not, check if they are an admin or creator of the group
    try:
        chat_admins = await context.bot.get_chat_administrators(chat_id)
        for admin in chat_admins:
            if admin.user.id == user_id:
                return True
    except Exception as e:
        # This can fail if in a private chat or if bot has no permissions
        logger.warning(f"Could not get chat admins for {chat_id}: {e}")
        
    return False

async def is_group_chat(update: Update) -> bool:
    """Checks if the command was used in a group or supergroup."""
    if update.message.chat.type in ['group', 'supergroup']:
        return True
    
    await update.message.reply_text("This command must be used in a group chat.")
    return False

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Hello! I am your new moderation bot.\n"
        "I am ready to protect this group.\n\n"
        "If you are a group admin, you can use these commands *in this chat*:\n"
        "• `/addblacklist [term]` - Add a term to the ban list\n"
        "• `/removeblacklist [term]` - Remove a term\n"
        "• `/listblacklist` - See all banned terms"
    )

async def add_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a term to this group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if in a group and if user is an admin
    if not await is_group_chat(update):
        return
    if not await is_admin(user_id, chat_id, context):
        await update.message.reply_text("You must be a group admin to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addblacklist [term]")
        return

    term = " ".join(context.args).lower()
    
    try:
        # Pass chat_id to the database function
        success = await asyncio.to_thread(add_to_blacklist, chat_id, term)
        
        if success:
            await update.message.reply_text(f"✅ Added '<code>{html.escape(term)}</code>' to this group's blacklist.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"'<code>{html.escape(term)}</code>' is already on this group's blacklist.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in add_blacklist_command: {e}")
        await update.message.reply_text("An error occurred while adding the term.")

async def remove_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a term from this group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if in a group and if user is an admin
    if not await is_group_chat(update):
        return
    if not await is_admin(user_id, chat_id, context):
        await update.message.reply_text("You must be a group admin to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeblacklist [term]")
        return

    term = " ".join(context.args).lower()
    
    try:
        # Pass chat_id to the database function
        success = await asyncio.to_thread(remove_from_blacklist, chat_id, term)
        
        if success:
            await update.message.reply_text(f"✅ Removed '<code>{html.escape(term)}</code>' from this group's blacklist.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"'<code>{html.escape(term)}</code>' was not found on this group's blacklist.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in remove_blacklist_command: {e}")
        await update.message.reply_text("An error occurred while removing the term.")

async def list_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all terms on this group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Check if in a group and if user is an admin
    if not await is_group_chat(update):
        return
    if not await is_admin(user_id, chat_id, context):
        await update.message.reply_text("You must be a group admin to use this command.")
        return

    try:
        # Pass chat_id to the database function
        terms = await asyncio.to_thread(get_blacklist, chat_id)
        
        if not terms:
            await update.message.reply_text("This group's blacklist is currently empty.")
            return

        message = "<b>Current Blacklisted Terms for this Group:</b>\n\n"
        
        # --- NOTE ---
        # This loop assumes your `get_blacklist` returns a list of rows,
        # and the term itself is the SECOND item (index 1) in each row.
        # e.g., [(1, 'term1', 12345), (2, 'term2', 12345)]
        #
        # If your function *only* returns a list of strings (e.g., ['term1', 'term2']),
        # you should change this loop to:
        #
        # for term in terms:
        #     escaped_term = html.escape(str(term))
        #     message += f"• <code>{escaped_term}</code>\n"
        #
        for row in terms:
            term_word = row[1] # Get the term from the database row
            escaped_term = html.escape(str(term_word)) 
            message += f"• <code>{escaped_term}</code>\n"

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in list_blacklist_command: {e}")
        await update.message.reply_text("An error occurred while fetching the blacklist.")
