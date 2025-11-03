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

# --- NEW: Load Super Admins from .env ---
admin_ids_str = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS_SET = set()

if not admin_ids_str:
    logger.warning("ADMIN_IDS environment variable is not set. Only group admins will be able to use commands (and only in groups).")
else:
    try:
        # Parse the comma-separated string into a set of integers
        ADMIN_IDS_SET = set(int(admin_id.strip()) for admin_id in admin_ids_str.split(',') if admin_id.strip().isdigit())
        if ADMIN_IDS_SET:
            logger.info(f"Loaded {len(ADMIN_IDS_SET)} Super Admin(s) from .env file.")
        else:
             logger.warning("ADMIN_IDS variable is empty or contains no valid IDs.")
    except ValueError:
        logger.error("Error: ADMIN_IDS contains invalid (non-numeric) values. Please check .env")
        ADMIN_IDS_SET = set()
