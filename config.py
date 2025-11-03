import os
from dotenv import load_dotenv

# Load variables from .env file if it exists (for local development)
load_dotenv()

# Get the bot token from environment variables
TOKEN = os.environ.get("BOT_TOKEN")

# Get the PostgreSQL database URL from environment variables
# Example format: "postgresql://user:password@hostname:port/database_name"
DATABASE_URL = os.environ.get("DATABASE_URL")
