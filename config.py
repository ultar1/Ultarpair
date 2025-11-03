import os
import logging
from dotenv import load_dotenv

# Load variables from .env file if it exists (for local development)
load_dotenv()
logger = logging.getLogger(__name__)

# Get the bot token from environment variables
TOKEN = os.environ.get("BOT_TOKEN")

# Get the PostgreSQL database URL from environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- Load Super Admins (Unchanged) ---
admin_ids_str = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS_SET = set()
if admin_ids_str:
    try:
        ADMIN_IDS_SET = set(int(admin_id.strip()) for admin_id in admin_ids_str.split(',') if admin_id.strip().isdigit())
        if ADMIN_IDS_SET:
            logger.info(f"Loaded {len(ADMIN_IDS_SET)} Super Admin(s).")
    except ValueError:
        logger.error("Error: ADMIN_IDS contains invalid (non-numeric) values.")
        ADMIN_IDS_SET = set()

# --- Webhook Configuration (THE FIX) ---

# We are hardcoding your production URL as requested.
# This is more reliable than using the environment variable.
WEBHOOK_URL = "https://ultarpair.onrender.com"

# This is a random string you create to make your webhook secure
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

# Log the loaded URL to confirm
if WEBHOOK_URL:
    logger.info(f"Webhook URL is set to: {WEBHOOK_URL}")
else:
    logger.error("!!! ERROR: WEBHOOK_URL is not set. !!!")
