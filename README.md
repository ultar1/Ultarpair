Telegram Group Moderation Bot (Database Version)
​This is a simple Telegram bot designed to auto-kick new users from a group if their username, first name, or last name contains a blacklisted term.
​This version is production-ready and uses:
​A PostgreSQL database to store the blacklist.
​Environment variables to keep secrets (bot token, database URL) safe.
​Admin Commands
​/start: Shows the welcome message and command list.
​/addblacklist <term>: Adds a new term to the blacklist database.
​/removeblacklist <term>: Removes a term from the blacklist database.
​/listblacklist: Shows all terms currently on the blacklist.
​🚀 Setup & Installation
​1. Get Secrets
​Bot Token: Chat with @BotFather on Telegram, create a /newbot, and copy the HTTP API Token.
​Database URL:
​You need a PostgreSQL database. You can get one for free from services like Railway, Render, or Supabase.
​After setting up a new database, find its Connection String or Database URL. It will look like postgresql://user:password@host:port/dbname.
​2. Set Up the Project
