import logging
from telegram import Update
from telegram.ext import CallbackContext
import database # Import our new database module

logger = logging.getLogger(__name__)

def check_new_member(update: Update, context: CallbackContext):
    """Checks new members against the blacklist from the database."""
    if not update.chat_member or not update.chat_member.new_chat_member:
        return

    new_member = update.chat_member.new_chat_member
    
    if new_member.status != "member":
        return
    
    old_status = update.chat_member.old_chat_member.status
    if old_status in ('creator', 'administrator', 'member'):
        return # User was already in the group
        
    user = new_member.user
    chat_id = update.effective_chat.id

    logger.info(f"Checking new user: {user.full_name} ({user.id}) in chat {chat_id}")

    # Collect all text to check
    text_to_check = []
    if user.username:
        text_to_check.append(user.username.lower())
    if user.first_name:
        text_to_check.append(user.first_name.lower())
    if user.last_name:
        text_to_check.append(user.last_name.lower())

    if not text_to_check:
        return

    user_full_text = " ".join(text_to_check)
    
    # Get the fresh blacklist from the database for every new user
    blacklist = database.get_blacklist()
    
    if not blacklist:
        return # Nothing to check against

    for blocked_term in blacklist:
        if blocked_term in user_full_text:
            logger.info(f"MATCH: User '{user_full_text}' matches term '{blocked_term}'")
            try:
                # KICK THE USER!
                context.bot.kick_chat_member(chat_id=chat_id, user_id=user.id)
                
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Removed user {user.full_name} for matching a blacklisted term."
                )
                logger.info(f"Successfully kicked user {user.id}")
                return
            
            except Exception as e:
                logger.error(f"Failed to kick user {user.id}: {e}")
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ **Action Failed!** ⚠️\nUser {user.full_name} matches the blacklist, but I could not remove them. "
                         "Please make sure I am an admin with 'Ban users' permission."
                )
                return
