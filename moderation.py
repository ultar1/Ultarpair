import logging
import html
import asyncio  # <-- Make sure this is imported
from telegram import Update
from telegram.ext import ContextTypes
import database 
from telegram.constants import ParseMode
from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)

async def check_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Checks new members. 
    1. Kicks bots if /antibot is on.
    2. Checks humans against the blacklist.
    """
    if not update.chat_member or not update.chat_member.new_chat_member:
        return

    new_member = update.chat_member.new_chat_member
    
    # Only check users who are newly joining as "member"
    if new_member.status != "member":
        return
    
    # Check old status to make sure they weren't already in the group
    old_status = update.chat_member.old_chat_member.status
    if old_status in ('creator', 'administrator', 'member'):
        return # User was already in the group, not a "new" join
        
    user = new_member.user
    chat_id = update.effective_chat.id

    # --- (NEW ANTI-BOT LOGIC) ---
    if user.is_bot:
        logger.info(f"New user is a bot: {user.full_name} ({user.id}) in chat {chat_id}")
        
        # Check if anti-bot is enabled for this group
        antibot_on = await asyncio.to_thread(database.is_antibot_enabled, chat_id)
        
        if antibot_on:
            logger.info(f"Anti-bot is ON for chat {chat_id}. Kicking bot.")
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                
                # Send a message that auto-deletes
                sent_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🤖 Anti-bot enabled. Removed bot {html.escape(user.full_name)}.",
                    parse_mode=ParseMode.HTML
                )
                await asyncio.sleep(5)
                await sent_msg.delete()
                
            except Exception as e:
                logger.error(f"Failed to kick bot {user.id}: {e}")
            
            return # IMPORTANT: Stop processing. Do not check bot against human blacklist.
        
        else:
            logger.info(f"Anti-bot is OFF for chat {chat_id}. Allowing bot.")
    
    # --- (END OF NEW ANTI-BOT LOGIC) ---
    
    # --- (EXISTING HUMAN BLACKLIST LOGIC) ---
    logger.info(f"Checking new human user: {user.full_name} ({user.id}) in chat {chat_id}")

    # Collect all text to check and convert to lowercase
    text_to_check = []
    if user.username:
        text_to_check.append(user.username.lower())
    if user.first_name:
        text_to_check.append(user.first_name.lower())
    if user.last_name:
        text_to_check.append(user.last_name.lower())

    # Create one single string to check against
    user_full_text = " ".join(text_to_check)

    if not user_full_text:
        return

    try:
        # Get blacklist for THIS specific chat
        blacklist = await asyncio.to_thread(database.get_blacklist, chat_id)
    except Exception as e:
        logger.error(f"Failed to get blacklist during new member check: {e}")
        return
    
    if not blacklist:
        return # Nothing to check against

    SIMILARITY_THRESHOLD = 90 

    for blocked_term in blacklist:
        # 'blocked_term' is already lowercase from your add_blacklist command
        
        # Use token_set_ratio to compare whole words, not partial strings.
        ratio = fuzz.token_set_ratio(blocked_term, user_full_text)
        
        if ratio >= SIMILARITY_THRESHOLD:
            logger.info(f"MATCH: User '{user_full_text}' matches term '{blocked_term}' with {ratio}% similarity")
            try:
                # KICK THE USER!
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                logger.info(f"Successfully kicked user {user.id}")

                # --- (THIS IS YOUR EXISTING AUTO-DELETE LOGIC) ---
                
                # 1. Send your new message and store the message object
                sent_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🤖 Auto-removal: {html.escape(user.full_name)}. (Blacklist match: <b>{blocked_term}</b>).",
                    parse_mode=ParseMode.HTML
                )
                
                # 2. Wait 5 seconds (asynchronously)
                await asyncio.sleep(5)
                
                # 3. Delete the message (with error handling)
                try:
                    await sent_message.delete()
                    logger.info(f"Auto-deleted kick message {sent_message.message_id}")
                except Exception as e:
                    logger.warning(f"Could not auto-delete kick message: {e}")
                
                return # Stop checking, user is gone
            
            except Exception as e:
                logger.error(f"Failed to kick user {user.id}: {e}")
                # This is the "failed to kick" message, we don't auto-delete this one
                # so the admin can see it.
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ <b>Action Failed!</b> ⚠️\n"
                         f"User {html.escape(user.full_name)} matches the blacklist, but I could not remove them. "
                         "Please make sure I am an admin with 'Ban users' permission.",
                    parse_mode=ParseMode.HTML
                )
                return
