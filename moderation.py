import logging
import html
import asyncio
import re  # <-- NEW
from datetime import datetime, timedelta, timezone  # <-- NEW
from telegram import Update, ChatPermissions  # <-- NEW
from telegram.ext import ContextTypes
import database
from telegram.constants import ParseMode
from fuzzywuzzy import fuzz
import config  # <-- NEW

logger = logging.getLogger(__name__)

# --- (NEW) Helper function, also found in commands.py ---
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

# --- (UPDATED) check_new_member ---

async def check_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Checks new members. 
    1. Kicks bots if /antibot is on.
    2. Checks humans against the blacklist.
    """
    if not update.chat_member or not update.chat_member.new_chat_member:
        return

    new_member = update.chat_member.new_chat_member
    
    if new_member.status != "member":
        return
    
    old_status = update.chat_member.old_chat_member.status
    if old_status in ('creator', 'administrator', 'member'):
        return
        
    user = new_member.user
    chat_id = update.effective_chat.id

    # --- (UPDATED ANTI-BOT LOGIC) ---
    if user.is_bot:
        logger.info(f"New user is a bot: {user.full_name} ({user.id}) in chat {chat_id}")
        
        # Check if anti-bot is enabled using the new settings function
        settings = await asyncio.to_thread(database.get_group_settings, chat_id)
        antibot_on = settings.get('antibot_enabled', False)
        
        if antibot_on:
            logger.info(f"Anti-bot is ON for chat {chat_id}. Kicking bot.")
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                
                sent_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🤖 Anti-bot enabled. Removed bot {html.escape(user.full_name)}.",
                    parse_mode=ParseMode.HTML
                )
                await asyncio.sleep(5)
                await sent_msg.delete()
                
            except Exception as e:
                logger.error(f"Failed to kick bot {user.id}: {e}")
            
            return
        
        else:
            logger.info(f"Anti-bot is OFF for chat {chat_id}. Allowing bot.")
    
    # --- (END OF ANTI-BOT LOGIC) ---
    
    # --- (EXISTING HUMAN BLACKLIST LOGIC) ---
    logger.info(f"Checking new human user: {user.full_name} ({user.id}) in chat {chat_id}")

    text_to_check = []
    if user.username:
        text_to_check.append(user.username.lower())
    if user.first_name:
        text_to_check.append(user.first_name.lower())
    if user.last_name:
        text_to_check.append(user.last_name.lower())

    user_full_text = " ".join(text_to_check)

    if not user_full_text:
        return

    try:
        blacklist = await asyncio.to_thread(database.get_blacklist, chat_id)
    except Exception as e:
        logger.error(f"Failed to get blacklist during new member check: {e}")
        return
    
    if not blacklist:
        return

    SIMILARITY_THRESHOLD = 90 

    for blocked_term in blacklist:
        ratio = fuzz.token_set_ratio(blocked_term, user_full_text)
        
        if ratio >= SIMILARITY_THRESHOLD:
            logger.info(f"MATCH: User '{user_full_text}' matches term '{blocked_term}' with {ratio}% similarity")
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                logger.info(f"Successfully kicked user {user.id}")

                sent_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🤖 Auto-removal: {html.escape(user.full_name)}. (Blacklist match: <b>{blocked_term}</b>).",
                    parse_mode=ParseMode.HTML
                )
                
                await asyncio.sleep(5)
                
                try:
                    await sent_message.delete()
                    logger.info(f"Auto-deleted kick message {sent_message.message_id}")
                except Exception as e:
                    logger.warning(f"Could not auto-delete kick message: {e}")
                
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

# --- (NEW) Message Handler ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    The main handler that checks every message for links or bad words.
    This runs *after* commands are processed.
    """
    # Don't process non-messages, or messages from admins
    # (We also check for text, as 'new chat member' is a 'message' with no text)
    if not update.message or not update.message.chat_id or not update.message.from_user or not update.message.text:
        return
        
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    # 1. Get group settings
    settings = await asyncio.to_thread(database.get_group_settings, chat_id)

    # 2. If all filters are off, stop immediately
    if not settings.get('antilink_enabled') and not settings.get('antiword_enabled'):
        return
        
    # 3. Don't filter admins
    if await is_admin(user_id, chat_id, context):
        return
        
    # --- 4. Anti-Word Check ---
    if settings.get('antiword_enabled'):
        words_blacklist = await asyncio.to_thread(database.get_antiword_list, chat_id)
        if words_blacklist and update.message.text:
            text_lower = update.message.text.lower()
            if any(word in text_lower for word in words_blacklist):
                logger.info(f"Anti-word violation by {user_id} in {chat_id}")
                await handle_violation(
                    "antiword", update, context, 
                    settings.get('antiword_warn_limit', 3)
                )
                return # Stop processing, message is gone

    # --- 5. Anti-Link Check ---
    if settings.get('antilink_enabled'):
        # Check for links
        # This checks for t.me, http://, https://, and domain.com
        # It now also checks entities for hidden links
        
        has_link = False
        text_to_check = (update.message.text or "").lower()
        
        # Check in plain text
        if re.search(r'(t\.me/|https?://|[\w-]+\.[\w-]+)', text_to_check):
            has_link = True
            
        # Check in message entities (for hidden links)
        if not has_link and update.message.entities:
            for entity in update.message.entities:
                if entity.type in ['url', 'text_link']:
                    has_link = True
                    if entity.type == 'text_link':
                        text_to_check += f" {entity.url.lower()}" # Add the hidden URL to our check
                    break # Found a link, no need to check more
        
        if has_link:
            # Link is found, check allowlist
            allowed_domains = await asyncio.to_thread(database.get_antilink_whitelist, chat_id)
            
            # Simple check: if any allowed domain is in the text, permit it
            if any(domain in text_to_check for domain in allowed_domains):
                logger.info(f"Allowed link posted by {user_id} in {chat_id}. Skipping.")
            else:
                logger.info(f"Anti-link violation by {user_id} in {chat_id}")
                await handle_violation(
                    "antilink", update, context, 
                    settings.get('antilink_warn_limit', 3)
                )
                return # Stop processing, message is gone
    
async def handle_violation(warn_type: str, update: Update, context: ContextTypes.DEFAULT_TYPE, warn_limit: int):
    """
    Handles the consequences of a violation (antilink/antiword).
    Deletes, warns, and mutes the user.
    """
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    user_name = update.message.from_user.full_name
    
    try:
        # 1. Delete the offending message
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message in {chat_id}: {e}")

    # 2. Add a warning
    new_warn_count = await asyncio.to_thread(database.add_user_warning, chat_id, user_id, warn_type)
    
    if new_warn_count == -1:
        logger.error(f"Failed to add warning for {user_id} in {chat_id}")
        return

    # 3. Check if warn limit is reached
    if new_warn_count >= warn_limit:
        logger.info(f"Warn limit reached for {user_id} in {chat_id}. Muting for 1 hour.")
        
        # Mute for 1 hour
        try:
            until_date = datetime.now(timezone.utc) + timedelta(hours=1)
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            
            # Reset warnings
            await asyncio.to_thread(database.reset_user_warnings, chat_id, user_id, warn_type)
            
            # Send mute message
            reason = "link spam" if warn_type == "antilink" else "bad words"
            sent_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔇 User {html.escape(user_name)} has been muted for 1 hour due to {reason}.",
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(10) # Keep this message longer
            await sent_msg.delete()
            
        except Exception as e:
            logger.error(f"Failed to mute {user_id} in {chat_id}: {e}")
            
    else:
        # Just send a warning
        reason = "Links" if warn_type == "antilink" else "Bad words"
        sent_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"{html.escape(user_name)}, {reason} are not allowed. "
                 f"(Warning {new_warn_count}/{warn_limit})",
            parse_mode=ParseMode.HTML
        )
        await asyncio.sleep(5) # Auto-delete warning
        await sent_msg.delete()
