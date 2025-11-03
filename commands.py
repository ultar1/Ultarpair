import logging
from telegram import Update
# Import the new ContextTypes
from telegram.ext import CallbackContext, ContextTypes
import database
from config import ADMIN_IDS_SET

logger = logging.getLogger(__name__)

# This function must now be ASYNC
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Checks if a user is authorized to run an admin command.
    """
    if not update.effective_user:
        return False  # Cannot identify user

    user_id = update.effective_user.id

    # 1. Check if user is a Super-Admin (from .env file)
    if user_id in ADMIN_IDS_SET:
        return True

    # 2. If not Super-Admin, check if they are in a private chat.
    if update.effective_chat.type == 'private':
        return False

    # 3. If in a group, check if they are a Group-Admin
    try:
        # This bot call must now be AWAITED
        member = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_id
        )
        is_group_admin = member.status in ('administrator', 'creator')
        return is_group_admin
    except Exception as e:
        logger.warning(f"Could not check admin status for {user_id} in chat {update.effective_chat.id}: {e}")
        return False

# --- Command Handlers ---
# All handlers are now 'async def' and use 'await'

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(start_message)

async def add_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a term to the blacklist database."""
    # We must 'await' the async is_admin function
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sorry, this command is for admins only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addblacklist <term_to_block>")
        return

    term_to_add = " ".join(context.args).lower()
    
    if database.add_to_blacklist(term_to_add):
        await update.message.reply_text(f"✅ Added '{term_to_add}' to the blacklist.")
    else:
        await update.message.reply_text(f"⚠️ '{term_to_add}' is already on the blacklist or an error occurred.")

async def remove_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a term from the blacklist database."""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sorry, this command is for admins only.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeblacklist <term_to_remove>")
        return

    term_to_remove = " ".join(context.args).lower()

    if database.remove_from_blacklist(term_to_remove):
        await update.message.reply_text(f"🗑️ Removed '{term_to_remove}' from the blacklist.")
    else:
        await update.message.reply_text(f"⚠️ '{term_to_remove}' was not found on the blacklist.")

async def list_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all terms on the blacklist from the database."""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sorry, this command is for admins only.")
        return

    blacklist = database.get_blacklist()
    if not blacklist:
        await update.message.reply_text("📋 The blacklist is currently empty.")
        return

    message = "Current blacklist:\n"
    for term in sorted(list(blacklist)):
        # Escape markdown characters
        escaped_term = term.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('-', '\\-').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('.', '\\.').replace('!', '\\!')
        message += f"- `{escaped_term}`\n"
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')
