import logging
from telegram import Update
from telegram.ext import CallbackContext
import database
from config import ADMIN_IDS_SET  # <-- Import the new Super Admin set

logger = logging.getLogger(__name__)

def is_admin(update: Update, context: CallbackContext) -> bool:
    """
    Checks if a user is authorized to run an admin command.
    Returns True if:
    1. The user's ID is in the ADMIN_IDS_SET (Super-Admin, can use in private chat).
    2. The user is an 'administrator' or 'creator' of the group (Group-Admin, can only use in the group).
    """
    if not update.effective_user:
        return False  # Cannot identify user

    user_id = update.effective_user.id

    # 1. Check if user is a Super-Admin (from .env file)
    if user_id in ADMIN_IDS_SET:
        return True

    # 2. If not Super-Admin, check if they are in a private chat.
    # At this point, only Super-Admins can use private chat.
    if update.effective_chat.type == 'private':
        return False

    # 3. If in a group, check if they are a Group-Admin
    try:
        member = context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_id
        )
        is_group_admin = member.status in ('administrator', 'creator')
        return is_group_admin
    except Exception as e:
        # This can fail if bot is not in the group or has no perms
        logger.warning(f"Could not check admin status for {user_id} in chat {update.effective_chat.id}: {e}")
        return False

# --- Command Handlers (No changes below, they just use is_admin) ---

def start_command(update: Update, context: CallbackContext):
    """Sends a welcome message."""
    start_message = (
        "👋 Hi! I am a moderation bot.\n"
        "Add me to your group and make me an admin with 'Ban users' permission.\n\n"
        "Commands:\n"
        "🔹 /addblacklist <term>\n"
        "🔹 /removeblacklist <term>\n"
        "🔹 /listblacklist\n\n"
        "Group admins can use these commands in the group. "
        "Super-Admins (from .env) can also use them in this private chat."
    )
    update.message.reply_text(start_message)

def add_blacklist_command(update: Update, context: CallbackContext):
    """Adds a term to the blacklist database."""
    if not is_admin(update, context):
        update.message.reply_text("❌ Sorry, this command is for admins only.")
        return

    if not context.args:
        update.message.reply_text("Usage: /addblacklist <term_to_block>")
        return

    term_to_add = " ".join(context.args).lower()
    
    if database.add_to_blacklist(term_to_add):
        update.message.reply_text(f"✅ Added '{term_to_add}' to the blacklist.")
    else:
        update.message.reply_text(f"⚠️ '{term_to_add}' is already on the blacklist or an error occurred.")

def remove_blacklist_command(update: Update, context: CallbackContext):
    """Removes a term from the blacklist database."""
    if not is_admin(update, context):
        update.message.reply_text("❌ Sorry, this command is for admins only.")
        return

    if not context.args:
        update.message.reply_text("Usage: /removeblacklist <term_to_remove>")
        return

    term_to_remove = " ".join(context.args).lower()

    if database.remove_from_blacklist(term_to_remove):
        update.message.reply_text(f"🗑️ Removed '{term_to_remove}' from the blacklist.")
    else:
        update.message.reply_text(f"⚠️ '{term_to_remove}' was not found on the blacklist.")

def list_blacklist_command(update: Update, context: CallbackContext):
    """Lists all terms on the blacklist from the database."""
    if not is_admin(update, context):
        update.message.reply_text("❌ Sorry, this command is for admins only.")
        return

    blacklist = database.get_blacklist()
    if not blacklist:
        update.message.reply_text("📋 The blacklist is currently empty.")
        return

    message = "Current blacklist:\n"
    # Need to escape characters for MarkdownV2
    for term in sorted(list(blacklist)):
        escaped_term = term.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')
        message += f"- `{escaped_term}`\n"
    
    update.message.reply_text(message, parse_mode='MarkdownV2')
