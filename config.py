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

# --- NEW: Webhook Configuration ---

# This is the public URL of your Render web service
# Render sets this automatically as 'RENDER_EXTERNAL_URL'
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

# This is a random string you create to make your webhook secure
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
