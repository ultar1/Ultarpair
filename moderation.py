import logging
import html
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
import database 
from telegram.constants import ParseMode
from fuzzywuzzy import fuzz  # <-- NEW: Import the fuzzy matching library

logger = logging.getLogger(__name__)

async def check_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks new members against the blacklist using fuzzy matching."""
    if not update.chat_member or not update.chat_member.new_chat_member:
        return

    new_member = update.chat_member.new_chat_member
    
    if new_member.status != "member":
        return
    
    old_status = update.chat_member.old_chat_member.status
    if old_status in ('creator', 'administrator', 'member'):
        return # User was already in the group, not a "new" join
        
    user = new_member.user
    chat_id = update.effective_chat.id

    logger.info(f"Checking new user: {user.full_name} ({user.id}) in chat {chat_id}")

    # Collect all text to check and convert to lowercase
    text_to_check = []
    if user.username:
        text_to_check.append(user.username.lower())
    if user.first_name:
        text_to_check.append(user.first_name.lower())
    if user.last_name:
        text_to_check.append(user.last_name.lower())

    # Create one single string to check against
    # e.g., "blessed lilian blessedlilian"
    user_full_text = " ".join(text_to_check)

    if not user_full_text:
        return

    try:
        # Get blacklist (non-blocking)
        blacklist = await asyncio.to_thread(database.get_blacklist)
    except Exception as e:
        logger.error(f"Failed to get blacklist during new member check: {e}")
        return
    
    if not blacklist:
        return # Nothing to check against

    # --- NEW FUZZY LOGIC ---
    # We set a "similarity" score. 90 means "90% similar".
    # This will catch "lilian" and "lillian" or "blessed" and "b1essed"
    SIMILARITY_THRESHOLD = 90 

    for blocked_term in blacklist:
        # 'blocked_term' is already lowercase from your add_blacklist command
        
        # This checks how similar the blocked_term is to parts of the user's name
        ratio = fuzz.partial_ratio(blocked_term, user_full_text)
        
        if ratio >= SIMILARITY_THRESHOLD:
            logger.info(f"MATCH: User '{user_full_text}' matches term '{blocked_term}' with {ratio}% similarity")
            try:
                # KICK THE USER!
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Removed user {html.escape(user.full_name)} for matching a blacklisted term (<b>{blocked_term}</b>).",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Successfully kicked user {user.id}")
                return
            
            except Exception as e:
                logger.error(f"Failed to kick user {user.id}: {e}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ <b>Action Failed!</b> ⚠️\n"
                         f"User {html.escape(user.full_name)} matches the blacklist, but I could not remove them. "
                         "Please make sure I am an admin with 'Ban users' permission.",
                    parse_mode=ParseMode.HTML
                )
                return

