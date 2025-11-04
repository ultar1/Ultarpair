import logging
import html
import asyncio
import re
from datetime import datetime, timedelta, timezone 
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
# --- (HERE ARE THE NEW IMPORTS) ---
from database import (
    add_to_blacklist, 
    remove_from_blacklist, 
    get_blacklist, 
    add_job,
    set_antibot_status,  # <-- NEW
    is_antibot_enabled   # <-- NEW
)
# --- (END OF NEW IMPORTS) ---
import config

# Set up logging
logger = logging.getLogger(__name__)

def parse_duration(text: str) -> timedelta | None:
    """
    Parses a human-readable duration string into a timedelta.
    Examples: "1 min", "5 hrs", "9 days"
    """
    if not text:
        return None
    
    match = re.match(r"(\d+)\s*(mins?|minutes?|m)$", text, re.IGNORECASE)
    if match:
        return timedelta(minutes=int(match.group(1)))
        
    match = re.match(r"(\d+)\s*(hrs?|hours?|h)$", text, re.IGNORECASE)
    if match:
        return timedelta(hours=int(match.group(1)))
        
    match = re.match(r"(\d+)\s*(days?|d)$", text, re.IGNORECASE)
    if match:
        return timedelta(days=int(match.group(1)))
        
    return None # Invalid format

# --- Helper Function ---

async def delete_and_reply(update: Update, text: str, parse_mode: str = None):
    """
    Smarter reply function.
    1. Sends a new reply from the bot.
    2. Deletes user's command (but ONLY in a group).
    3. Deletes the bot's reply after 5 seconds (but ONLY in a group).
    """
    is_private = update.message.chat.type == 'private'
    
    # 1. Reply FIRST (to avoid 'message not found' error)
    try:
        sent_message = await update.message.reply_text(text=text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Failed to send reply message: {e}")
        return

    # 2. Delete user's command *after* replying
    if not is_private:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete user's command message: {e}")
    
    # 3. Auto-delete bot's reply (only in group)
    if not is_private:
        await asyncio.sleep(5)
        
        try:
            await sent_message.delete()
        except Exception as e:
            logger.warning(f"Failed to auto-delete bot reply: {e}")


async def is_admin(user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if a user is an admin (Super Admin or Group Admin)."""
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
    """Checks if the command was used in a group. If not, sends a reply."""
    if update.message.chat.type in ['group', 'supergroup']:
        return True
    await delete_and_reply(update, "This command must be used in a group chat.")
    return False

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    # --- (UPDATED START MESSAGE) ---
    start_message = (
        "Hello! I am your new moderation bot.\n"
        "I am ready to protect this group.\n\n"
        "If you are a group admin, you can use these commands *in a group*:\n"
        "• `/addblacklist [term]` - Add a term to the ban list\n"
        "• `/removeblacklist [term]` - Remove a term\n"
        "• `/listblacklist` - See all banned terms\n"
        "• `/silent [duration]` - (Reply) Mute a user\n"
        "• `/pin [duration]` - (Reply) Pin a message\n"
        "• `/antibot [on/off]` - Enable/disable anti-bot" # <-- NEW
    )
    # --- (END OF UPDATE) ---
    await delete_and_reply(update, start_message, parse_mode=ParseMode.MARKDOWN)

async def add_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Adds a term to the group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
        
    if not context.args:
        await delete_and_reply(update, "Usage: /addblacklist [term]")
        return
        
    term = " ".join(context.args).lower()
    
    try:
        success = await asyncio.to_thread(add_to_blacklist, chat_id, term)
        if success:
            await delete_and_reply(update, f"✅ Added '<code>{html.escape(term)}</code>' to this group's blacklist.", parse_mode=ParseMode.HTML)
        else:
            await delete_and_reply(update, f"'<code>{html.escape(term)}</code>' is already on this group's blacklist.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in add_blacklist_command: {e}")
        await delete_and_reply(update, "An error occurred while adding the term.")

async def remove_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Removes a term from the group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
        
    if not context.args:
        await delete_and_reply(update, "Usage: /removeblacklist [term]")
        return
        
    term = " ".join(context.args).lower()
    
    try:
        success = await asyncio.to_thread(remove_from_blacklist, chat_id, term)
        if success:
            await delete_and_reply(update, f"✅ Removed '<code>{html.escape(term)}</code>' from this group's blacklist.", parse_mode=ParseMode.HTML)
        else:
            await delete_and_reply(update, f"'<code>{html.escape(term)}</code>' was not found on this group's blacklist.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error in remove_blacklist_command: {e}")
        await delete_and_reply(update, "An error occurred while removing the term.")

async def list_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Lists all terms on the group's blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
        
    try:
        terms = await asyncio.to_thread(get_blacklist, chat_id)
        if not terms:
            await delete_and_reply(update, "This group's blacklist is currently empty.")
            return
            
        message = "<b>Current Blacklisted Terms for this Group:</b>\n\n"
        for term in terms:
            escaped_term = html.escape(str(term)) 
            message += f"• <code>{escaped_term}</code>\n"
            
        await delete_and_reply(update, message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in list_blacklist_command: {e}")
        await delete_and_reply(update, "An error occurred while fetching the blacklist.")

# --- Job-based Commands ---

async def silent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Mutes a user and schedules a persistent unmute job."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
    if not update.message.reply_to_message:
        await delete_and_reply(update, "Usage: Reply to a user's message with `/silent [duration]` (e.g., /silent 5 hrs).")
        return
        
    target_user = update.message.reply_to_message.from_user
    duration_text = " ".join(context.args)
    duration = parse_duration(duration_text)
    
    if not duration:
        await delete_and_reply(update, "Invalid duration format. Use 'mins', 'hrs', or 'days'.\nExample: `/silent 5 hrs`")
        return
        
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        
        run_at = datetime.now(timezone.utc) + duration
        
        await asyncio.to_thread(
            add_job,
            job_type="unmute",
            chat_id=chat_id,
            target_id=target_user.id,
            run_at=run_at
        )
        
        await delete_and_reply(update, f"🔇 User {html.escape(target_user.full_name)} has been muted for {duration_text}.")
        
    except Exception as e:
        logger.error(f"Error in silent_command: {e}", exc_info=True)
        await delete_and_reply(update, f"Failed to mute user. Do I have 'Restrict Users' permission?")

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Pins a message and schedules a persistent unpin job."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    
    if not await is_admin(user_id, chat_id, context):
        try: await update.message.delete()
        except Exception: pass
        return
    if not update.message.reply_to_message:
        try: await update.message.delete()
        except Exception: pass
        return
        
    target_message = update.message.reply_to_message
    duration_text = " ".join(context.args)
    duration = parse_duration(duration_text)
    
    if not duration:
        try: await update.message.delete()
        except Exception: pass
        return

    try:
        await context.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=target_message.message_id,
            disable_notification=True
        )
        
        run_at = datetime.now(timezone.utc) + duration
        
        await asyncio.to_thread(
            add_job,
            job_type="unpin",
            chat_id=chat_id,
            target_id=target_message.message_id,
            run_at=run_at
        )
        
        await update.message.delete()
        
    except Exception as e:
        logger.error(f"Error in pin_command: {e}", exc_info=True)
        try: await update.message.delete()
        except Exception: pass

# --- (NEW /antibot COMMAND) ---
async def antibot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Toggles the anti-bot feature on or off."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
        
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        # Check current status if no args given
        try:
            current_status = await asyncio.to_thread(is_antibot_enabled, chat_id)
            status_str = "ON" if current_status else "OFF"
            await delete_and_reply(update, f"Usage: `/antibot on` or `/antibot off`\n(Current status is: **{status_str}**)")
        except Exception as e:
            logger.error(f"Error checking antibot status: {e}")
            await delete_and_reply(update, "Usage: `/antibot on` or `/antibot off`")
        return
        
    new_status_str = context.args[0].lower()
    new_status_bool = True if new_status_str == 'on' else False
    
    try:
        success = await asyncio.to_thread(set_antibot_status, chat_id, new_status_bool)
        if success:
            if new_status_bool:
                await delete_and_reply(update, "✅ Anti-bot feature has been **enabled**.")
            else:
                await delete_and_reply(update, "❌ Anti-bot feature has been **disabled**.")
        else:
            await delete_and_reply(update, "Failed to update anti-bot status. Check logs.")
            
    except Exception as e:
        logger.error(f"Error in antibot_command: {e}")
        await delete_and_reply(update, "An error occurred while setting anti-bot status.")
# --- (END OF NEW COMMAND) ---
