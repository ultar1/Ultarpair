import logging
from telegram import Update
from telegram.ext import CallbackContext
import database  # Import our new database module

logger = logging.getLogger(__name__)

def is_admin(update: Update, context: CallbackContext) -> bool:
    """Check if the user sending the command is an admin or creator."""
    if not update.effective_chat or not update.effective_user:
        return False

    if update.effective_chat.type == 'private':
        return True # Allow use in private chat

    try:
        member = context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id
        )
        return member.status in ('administrator', 'creator')
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

# --- Command Handlers ---

def start_command(update: Update, context: CallbackContext):
    """Sends a welcome message."""
    update.message.reply_text(
        "👋 Hi! I am a moderation bot using a database.\n"
        "Add me to your group and make me an admin with 'Ban users' permission.\n\n"
        "Admin commands:\n"
        "🔹 /addblacklist <term>\n"
        "🔹 /removeblacklist <term>\n"
        "🔹 /listblacklist"
    )

def add_blacklist_command(update: Update, context: CallbackContext):
    """Adds a term to the blacklist database."""
    if not is_admin(update, context):
        update.message.reply_text("❌ Sorry, only group admins can use this command.")
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
        update.message.reply_text("❌ Sorry, only group admins can use this command.")
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
        update.message.reply_text("❌ Sorry, only group admins can use this command.")
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
