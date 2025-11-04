import logging
import html
import asyncio
import re
from datetime import datetime, timedelta, timezone 
from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
# --- (CRITICAL FIX: CORRECT IMPORTS LIST) ---
from database import (
    add_to_blacklist, 
    remove_from_blacklist, 
    get_blacklist, 
    add_job,
    set_group_setting,
    get_group_settings,
    add_antiword,
    remove_antiword,
    get_antiword_list,
    add_antilink_whitelist,
    remove_antilink_whitelist,
    get_antilink_whitelist,
    set_welcome_message  # <-- Import database function
)
# --- (END OF FIX) ---
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

# --- (NEW) URL Parser Helper ---
async def get_clean_url(url: str) -> str | None:
    """Cleans a URL and extracts the base domain."""
    if not url:
        return None
    try:
        # Add http if missing for parsing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        
        # Get domain (e.g., 'google.com', 'www.bbc.co.uk')
        domain = parsed_url.netloc
        
        # Optional: Remove 'www.'
        if domain.startswith('www.'):
            domain = domain[4:]
            
        return domain.lower()
    except Exception as e:
        logger.error(f"Failed to parse domain from url: {url} | Error: {e}")
        return None


# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    # --- (UPDATED START MESSAGE) ---
    start_message = (
        "Hello! I am your new moderation bot. I am ready to protect this group.\n\n"
        "**Admin Commands:**\n"
        "• `/antibot [on/off]` - Toggle bot kicking.\n"
        "• `/antilink [on/off]` - Toggle link deletion.\n"
        "• `/antiword [on/off]` - Toggle bad word deletion.\n"
        "• 👋 `/welcome [on/off]` - Toggle welcome messages.\n"
        "\n**Content Setup:**\n"
        "• `/setwelcome [message]` - Set the welcome message.\n"
        "• `/antiword add [word]` - Add a word to filter.\n"
        "• `/antilink allow [url]` - Allow a domain.\n"
        "\n**Blacklist Commands:**\n"
        "• `/addblacklist [term]` - Ban a name/username.\n"
        "• `/removeblacklist [term]` - Unban a name/username.\n"
        "\n**Moderation Actions:**\n"
        "• `/silent [duration]` - (Reply) Mute a user.\n"
        "• `/pin [duration]` - (Reply) Pin a message.\n"
        "\n**List Commands:**\n"
        "• `/listblacklist` - Show banned name list.\n"
        "• `/antiword list` - Show filtered word list.\n"
        "• `/antilink list` - Show allowed domain list."
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
    """(Admin) Mutes a user using Telegram's built-in scheduler."""
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
    
    if not duration_text: # Handle /silent with no duration (permanent)
        duration = None
        duration_text = "permanently"
    else:
        duration = parse_duration(duration_text)
        if not duration:
            await delete_and_reply(update, "Invalid duration format. Use 'mins', 'hrs', or 'days'.\nExample: `/silent 5 hrs` or `/silent` (for permanent).")
            return

    try:
        # --- (BUG FIX: Using Telegram's built-in scheduler) ---
        if duration:
            until_date = datetime.now(timezone.utc) + duration
        else:
            until_date = None # None means "forever"
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        # --- (END OF BUG FIX) ---
        
        await delete_and_reply(update, f"🔇 User {html.escape(target_user.full_name)} has been muted {duration_text}.")
        
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
            job_type="unpin", # This is the only job type handled by the scheduler
            chat_id=chat_id,
            target_id=target_message.message_id,
            run_at=run_at
        )
        
        await update.message.delete()
        
    except Exception as e:
        logger.error(f"Error in pin_command: {e}", exc_info=True)
        try: await update.message.delete()
        except Exception: pass

# --- (UPDATED) /antibot Command ---
async def antibot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Toggles the anti-bot feature on or off."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
        
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        # Check current status
        try:
            settings = await asyncio.to_thread(get_group_settings, chat_id)
            status_str = "ON" if settings.get('antibot_enabled') else "OFF"
            await delete_and_reply(update, f"Usage: `/antibot on` or `/antibot off`\n(Current status is: **{status_str}**)")
        except Exception as e:
            logger.error(f"Error checking antibot status: {e}")
            await delete_and_reply(update, "Usage: `/antibot on` or `/antibot off`")
        return
        
    new_status_str = context.args[0].lower()
    new_status_bool = True if new_status_str == 'on' else False
    
    try:
        # Use the *new* database function
        success = await asyncio.to_thread(set_group_setting, chat_id, "antibot_enabled", new_status_bool)
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


# --- (NEW) /antilink Command ---
async def antilink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Toggles /antilink or manages its whitelist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
    
    if not context.args:
        # Show current settings
        settings = await asyncio.to_thread(get_group_settings, chat_id)
        status_str = "ON" if settings.get('antilink_enabled') else "OFF"
        await delete_and_reply(update, f"Usage: `/antilink [on/off/allow/disallow/list]`\n(Current status: **{status_str}**)")
        return
        
    action = context.args[0].lower()
    
    # --- /antilink [on/off] ---
    if action in ['on', 'off']:
        new_status_bool = True if action == 'on' else False
        success = await asyncio.to_thread(set_group_setting, chat_id, "antilink_enabled", new_status_bool)
        if success:
            await delete_and_reply(update, f"✅ Anti-link feature has been **{action.upper()}**.")
        else:
            await delete_and_reply(update, "Failed to update anti-link status. Check logs.")
        return

    # --- /antilink allow [url] ---
    if action == 'allow':
        if len(context.args) < 2:
            await delete_and_reply(update, "Usage: `/antilink allow [domain.com]`")
            return
        domain = await get_clean_url(context.args[1])
        if not domain:
            await delete_and_reply(update, "Invalid URL format. Please provide a domain like `google.com`")
            return
        
        success = await asyncio.to_thread(add_antilink_whitelist, chat_id, domain)
        if success:
            await delete_and_reply(update, f"✅ Domain ` {domain} ` added to the allowlist.")
        else:
            await delete_and_reply(update, f"`{domain}` is already on the allowlist.")
        return

    # --- /antilink disallow [url] ---
    if action == 'disallow':
        if len(context.args) < 2:
            await delete_and_reply(update, "Usage: `/antilink disallow [domain.com]`")
            return
        domain = await get_clean_url(context.args[1])
        if not domain:
            await delete_and_reply(update, "Invalid URL format. Please provide a domain like `google.com`")
            return
            
        success = await asyncio.to_thread(remove_antilink_whitelist, chat_id, domain)
        if success:
            await delete_and_reply(update, f"✅ Domain ` {domain} ` removed from the allowlist.")
        else:
            await delete_and_reply(update, f"`{domain}` was not on the allowlist.")
        return

    # --- /antilink list ---
    if action == 'list':
        domains = await asyncio.to_thread(get_antilink_whitelist, chat_id)
        if not domains:
            await delete_and_reply(update, "The anti-link allowlist is empty.")
            return
        message = "<b>Allowed Domains:</b>\n\n"
        message += "\n".join(f"• <code>{html.escape(d)}</code>" for d in sorted(domains))
        await delete_and_reply(update, message, parse_mode=ParseMode.HTML)
        return

    await delete_and_reply(update, "Unknown command. Use `/antilink [on/off/allow/disallow/list]`")

# --- (NEW) /antiword Command ---
async def antiword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Toggles /antiword or manages its blacklist."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
    
    if not context.args:
        # Show current settings
        settings = await asyncio.to_thread(get_group_settings, chat_id)
        status_str = "ON" if settings.get('antiword_enabled') else "OFF"
        await delete_and_reply(update, f"Usage: `/antiword [on/off/add/remove/list]`\n(Current status: **{status_str}**)")
        return
        
    action = context.args[0].lower()
    
    # --- /antiword [on/off] ---
    if action in ['on', 'off']:
        new_status_bool = True if action == 'on' else False
        success = await asyncio.to_thread(set_group_setting, chat_id, "antiword_enabled", new_status_bool)
        if success:
            await delete_and_reply(update, f"✅ Anti-word feature has been **{action.upper()}**.")
        else:
            await delete_and_reply(update, "Failed to update anti-word status. Check logs.")
        return

    # --- /antiword add [word] ---
    if action == 'add':
        if len(context.args) < 2:
            await delete_and_reply(update, "Usage: `/antiword add [word]`")
            return
        word = " ".join(context.args[1:]).lower() # Allow multi-word phrases
        
        success = await asyncio.to_thread(add_antiword, chat_id, word)
        if success:
            await delete_and_reply(update, f"✅ Word ` {html.escape(word)} ` added to the filter.", parse_mode=ParseMode.HTML)
        else:
            await delete_and_reply(update, f"`{html.escape(word)}` is already on the filter list.", parse_mode=ParseMode.HTML)
        return

    # --- /antiword remove [word] ---
    if action == 'remove':
        if len(context.args) < 2:
            await delete_and_reply(update, "Usage: `/antiword remove [word]`")
            return
        word = " ".join(context.args[1:]).lower()
            
        success = await asyncio.to_thread(remove_antiword, chat_id, word)
        if success:
            await delete_and_reply(update, f"✅ Word ` {html.escape(word)} ` removed from the filter.", parse_mode=ParseMode.HTML)
        else:
            await delete_and_reply(update, f"`{html.escape(word)}` was not on the filter list.", parse_mode=ParseMode.HTML)
        return

    # --- /antiword list ---
    if action == 'list':
        words = await asyncio.to_thread(get_antiword_list, chat_id)
        if not words:
            await delete_and_reply(update, "The anti-word filter list is empty.")
            return
        message = "<b>Filtered Words:</b>\n\n"
        message += "\n".join(f"• <code>{html.escape(w)}</code>" for w in sorted(words))
        await delete_and_reply(update, message, parse_mode=ParseMode.HTML)
        return

    await delete_and_reply(update, "Unknown command. Use `/antiword [on/off/add/remove/list]`")


# --- (NEW) /welcome Command ---
async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Toggles the welcome message feature on or off."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return
        
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        # Check current status
        try:
            settings = await asyncio.to_thread(get_group_settings, chat_id)
            status_str = "ON" if settings.get('welcome_enabled') else "OFF"
            await delete_and_reply(update, f"Usage: `/welcome on` or `/welcome off`\n(Current status is: **{status_str}**)")
        except Exception as e:
            logger.error(f"Error checking welcome status: {e}")
            await delete_and_reply(update, "Usage: `/welcome on` or `/welcome off`")
        return
        
    new_status_str = context.args[0].lower()
    new_status_bool = True if new_status_str == 'on' else False
    
    try:
        success = await asyncio.to_thread(set_group_setting, chat_id, "welcome_enabled", new_status_bool)
        if success:
            if new_status_bool:
                await delete_and_reply(update, "✅ Welcome messages have been **enabled**.\nUse `/setwelcome` to create your message.")
            else:
                await delete_and_reply(update, "❌ Welcome messages have been **disabled**.")
        else:
            await delete_and_reply(update, "Failed to update welcome status. Check logs.")
            
    except Exception as e:
        logger.error(f"Error in welcome_command: {e}")
        await delete_and_reply(update, "An error occurred while setting welcome status.")

async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Sets the welcome message for the group."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not await is_group_chat(update): return
    if not await is_admin(user_id, chat_id, context):
        await delete_and_reply(update, "You must be a group admin to use this command.")
        return

    if not context.args:
        await delete_and_reply(update, 
            "Usage: `/setwelcome [message]`\n\n"
            "You can use placeholders:\n"
            "`{user_name}` - The new user's full name.\n"
            "`{chat_name}` - The group's name.\n\n"
            "Example: `/setwelcome Welcome {user_name} to {chat_name}!`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    # Get the raw message text after the command
    welcome_message = update.message.text.split(maxsplit=1)[1]
    
    try:
        success = await asyncio.to_thread(set_welcome_message, chat_id, welcome_message)
        if success:
            await delete_and_reply(update, "✅ Welcome message has been updated!")
        else:
            await delete_and_reply(update, "Failed to update welcome message. Check logs.")
    except Exception as e:
        logger.error(f"Error in setwelcome_command: {e}")
        await delete_and_reply(update, "An error occurred while setting the message.")
