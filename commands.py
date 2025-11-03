import logging
import html
import asyncio  # <-- You MUST import this
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import add_to_blacklist, remove_from_blacklist, get_blacklist
import config

# Set up logging
logger = logging.getLogger(__name__)

# --- Admin Check ---
async def is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the user is an admin (in config or a group admin)."""
    
    # 1. Check if they are a Super Admin (from .env)
    if user_id in config.ADMIN_IDS_SET:
        return True
    
    # 2. If not, check if they are an admin of the group
    # This part is more complex and requires checking chat admins.
    # For now, we will stick to Super Admins for private commands.
        
    return False

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Hello! I am your new moderation bot.\n"
        "I am ready to protect this group.\n\n"
        "If you are an admin, you can chat with me privately and use:\n"
        "/addblacklist [term] - Add a term to the ban list\n"
        "/removeblacklist [term] - Remove a term\n"
        "/listblacklist - See all banned terms"
    )

async def add_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a term to the blacklist."""
    user_id = update.effective_user.id
    
    if not await is_admin(user_id, context):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addblacklist [term]")
        return

    term = " ".join(context.args).lower()
    
    try:
        # --- FIX: 1) Typo removed, 2) Wrapped in async thread ---
        success = await asyncio.to_thread(add_to_blacklist, term)
        
        if success:
            await update.message.reply_text(f"✅ Added '{term}' to the blacklist.")
        else:
            await update.message.reply_text(f"'{term}' is already on the blacklist.")
    except Exception as e:
        logger.error(f"Error in add_blacklist_command: {e}")
        await update.message.reply_text("An error occurred while adding the term.")

async def remove_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a term from the blacklist."""
    user_id = update.effective_user.id
    
    if not await is_admin(user_id, context):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeblacklist [term]")
        return

    term = " ".join(context.args).lower()
    
    try:
        # --- FIX: Wrapped in async thread ---
        success = await asyncio.to_thread(remove_from_blacklist, term)
        
        if success:
            await update.message.reply_text(f"✅ Removed '{term}' from the blacklist.")
        else:
            await update.message.reply_text(f"'{term}' was not found on the blacklist.")
    except Exception as e:
        logger.error(f"Error in remove_blacklist_command: {e}")
        await update.message.reply_text("An error occurred while removing the term.")

async def list_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all terms on the blacklist."""
    user_id = update.effective_user.id
    
    if not await is_admin(user_id, context):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        # --- FIX: Wrapped in async thread ---
        terms = await asyncio.to_thread(get_blacklist)
        
        if not terms:
            await update.message.reply_text("The blacklist is currently empty.")
            return

        message = "<b>Current Blacklisted Terms:</b>\n\n"
        
        # --- FIX: The broken example line is GONE ---
        for term in terms:
            escaped_term = html.escape(str(term)) 
            message += f"• <code>{escaped_term}</code>\n"

        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in list_blacklist_command: {e}")
        await update.message.reply_text("An error occurred while fetching the blacklist.")


