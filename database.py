import psycopg2
import logging
import psycopg2.extras 
from config import DATABASE_URL
from datetime import datetime 

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Blacklist table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    id SERIAL PRIMARY KEY,
                    term TEXT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    UNIQUE(term, chat_id)
                );
            """)
            
            # Job scheduling table (for unpin)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id SERIAL PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    target_id BIGINT NOT NULL,
                    run_at TIMESTAMPTZ NOT NULL
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_run_at ON scheduled_jobs (run_at);
            """)
            
            # --- (TABLES FOR NEW FEATURES) ---
            
            # 1. Drop the old simple group_settings table if it exists
            # This ensures we get the new columns (welcome_message, etc.)
            cur.execute("DROP TABLE IF EXISTS group_settings;")

            # 2. Create the new, complete group_settings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS group_settings (
                    chat_id BIGINT PRIMARY KEY,
                    antibot_enabled BOOLEAN DEFAULT FALSE,
                    antilink_enabled BOOLEAN DEFAULT FALSE,
                    antiword_enabled BOOLEAN DEFAULT FALSE,
                    antilink_warn_limit SMALLINT DEFAULT 3,
                    antiword_warn_limit SMALLINT DEFAULT 3,
                    welcome_enabled BOOLEAN DEFAULT FALSE,  
                    welcome_message TEXT DEFAULT NULL       
                );
            """)
            
            # 3. Create the new antiword_blacklist table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS antiword_blacklist (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    word TEXT NOT NULL,
                    UNIQUE(chat_id, word)
                );
            """)
        
            # 4. Create the new antilink_whitelist table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS antilink_whitelist (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    domain TEXT NOT NULL,
                    UNIQUE(chat_id, domain)
                );
            """)
        
            # 5. Create the new user_warnings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_warnings (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    warn_type TEXT NOT NULL,
                    warn_count SMALLINT DEFAULT 1,
                    UNIQUE(chat_id, user_id, warn_type)
                );
            """)
            
            conn.commit()
            logger.info("Database tables initialized/verified.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
    finally:
        conn.close()

# --- Blacklist Functions ---

def add_to_blacklist(chat_id: int, term: str) -> bool:
    sql = "INSERT INTO blacklist (chat_id, term) VALUES (%s, %s) ON CONFLICT (chat_id, term) DO NOTHING"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, term.lower()))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error adding to blacklist: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def remove_from_blacklist(chat_id: int, term: str) -> bool:
    sql = "DELETE FROM blacklist WHERE chat_id = %s AND term = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, term.lower()))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing from blacklist: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_blacklist(chat_id: int) -> set:
    sql = "SELECT term FROM blacklist WHERE chat_id = %s"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (chat_id,))
            results = {row['term'] for row in cur.fetchall()} 
            return results
    except Exception as e:
        logger.error(f"Error getting blacklist: {e}")
        return set()
    finally:
        conn.close()

# --- Job Functions ---

def add_job(job_type: str, chat_id: int, target_id: int, run_at: 'datetime') -> bool:
    """Adds a new job to the database."""
    
    if job_type not in ['unpin']: # Only unpin jobs are stored here
        logger.error(f"Invalid job_type: {job_type}")
        return False
        
    sql = "INSERT INTO scheduled_jobs (job_type, chat_id, target_id, run_at) VALUES (%s, %s, %s, %s)"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (job_type, chat_id, target_id, run_at))
            conn.commit()
            logger.info(f"Added job: {job_type} for {chat_id} at {run_at}")
            return True
    except Exception as e:
        logger.error(f"Error adding job: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_due_jobs() -> list['psycopg2.extras.DictRow']:
    """Gets all due 'unpin' jobs."""
    sql = """
        SELECT * FROM scheduled_jobs 
        WHERE run_at <= NOW() AND job_type = 'unpin'
        ORDER BY run_at 
        FOR UPDATE SKIP LOCKED
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql)
            jobs = cur.fetchall()
            conn.commit()
            return jobs
    except Exception as e:
        logger.error(f"Error getting due jobs: {e}")
        conn.rollback()
        return []
    finally:
        conn.close()
        
def delete_job(job_id: int):
    """Deletes a job from the database, typically after it has run."""
    sql = "DELETE FROM scheduled_jobs WHERE id = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        conn.rollback()
    finally:
        conn.close()

# --- Group Settings ---

def set_group_setting(chat_id: int, setting: str, value) -> bool:
    """Dynamically sets a single group setting. Returns True on success."""
    
    # Allowlist of setting columns to prevent SQL injection
    allowed_settings = {
        "antibot_enabled", "antilink_enabled", "antiword_enabled", 
        "antilink_warn_limit", "antiword_warn_limit",
        "welcome_enabled"  # <-- ADDED
    }
    if setting not in allowed_settings:
        logger.error(f"Invalid setting name: {setting}")
        return False

    sql = f"""
        INSERT INTO group_settings (chat_id, {setting})
        VALUES (%s, %s)
        ON CONFLICT (chat_id)
        DO UPDATE SET {setting} = EXCLUDED.{setting};
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, value))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error in set_group_setting for {setting}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def set_welcome_message(chat_id: int, message: str) -> bool:
    """Sets the welcome message for a group."""
    sql = """
        INSERT INTO group_settings (chat_id, welcome_message)
        VALUES (%s, %s)
        ON CONFLICT (chat_id)
        DO UPDATE SET welcome_message = EXCLUDED.welcome_message;
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, message))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error in set_welcome_message: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_group_settings(chat_id: int) -> dict:
    """Gets all settings for a group. Returns a dict with defaults."""
    defaults = {
        "antibot_enabled": False,
        "antilink_enabled": False,
        "antiword_enabled": False,
        "antilink_warn_limit": 3,
        "antiword_warn_limit": 3,
        "welcome_enabled": False,
        "welcome_message": None
    }
    
    sql = "SELECT * FROM group_settings WHERE chat_id = %s"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (chat_id,))
            result = cur.fetchone()
            if result:
                for key in defaults:
                    if key in result and result[key] is not None:
                        defaults[key] = result[key]
            return defaults
    except Exception as e:
        logger.error(f"Error in get_group_settings: {e}")
        return defaults
    finally:
        conn.close()

# --- Anti-Word ---

def add_antiword(chat_id: int, word: str) -> bool:
    sql = "INSERT INTO antiword_blacklist (chat_id, word) VALUES (%s, %s) ON CONFLICT DO NOTHING"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, word.lower()))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error in add_antiword: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def remove_antiword(chat_id: int, word: str) -> bool:
    sql = "DELETE FROM antiword_blacklist WHERE chat_id = %s AND word = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, word.lower()))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error in remove_antiword: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_antiword_list(chat_id: int) -> set:
    sql = "SELECT word FROM antiword_blacklist WHERE chat_id = %s"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (chat_id,))
            return {row['word'] for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"Error in get_antiword_list: {e}")
        return set()
    finally:
        conn.close()

# --- Anti-Link ---

def add_antilink_whitelist(chat_id: int, domain: str) -> bool:
    sql = "INSERT INTO antilink_whitelist (chat_id, domain) VALUES (%s, %s) ON CONFLICT DO NOTHING"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, domain.lower()))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error in add_antilink_whitelist: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def remove_antilink_whitelist(chat_id: int, domain: str) -> bool:
    sql = "DELETE FROM antilink_whitelist WHERE chat_id = %s AND domain = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, domain.lower()))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error in remove_antilink_whitelist: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_antilink_whitelist(chat_id: int) -> set:
    sql = "SELECT domain FROM antilink_whitelist WHERE chat_id = %s"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (chat_id,))
            return {row['domain'] for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"Error in get_antilink_whitelist: {e}")
        return set()
    finally:
        conn.close()

# --- User Warnings ---

def get_user_warnings(chat_id: int, user_id: int, warn_type: str) -> int:
    """Gets the current warning count for a user and type. Defaults to 0."""
    sql = "SELECT warn_count FROM user_warnings WHERE chat_id = %s AND user_id = %s AND warn_type = %s"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (chat_id, user_id, warn_type))
            result = cur.fetchone()
            return result['warn_count'] if result else 0
    except Exception as e:
        logger.error(f"Error in get_user_warnings: {e}")
        return 0
    finally:
        conn.close()

def add_user_warning(chat_id: int, user_id: int, warn_type: str) -> int:
    """Adds a warning and returns the NEW warning count."""
    sql = """
        INSERT INTO user_warnings (chat_id, user_id, warn_type, warn_count)
        VALUES (%s, %s, %s, 1)
        ON CONFLICT (chat_id, user_id, warn_type)
        DO UPDATE SET warn_count = user_warnings.warn_count + 1
        RETURNING warn_count;
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(sql, (chat_id, user_id, warn_type))
            new_count = cur.fetchone()['warn_count']
            conn.commit()
            return new_count
    except Exception as e:
        logger.error(f"Error in add_user_warning: {e}")
        conn.rollback()
        return -1 # Return -1 on error
    finally:
        conn.close()

def reset_user_warnings(chat_id: int, user_id: int, warn_type: str):
    """Resets a user's warnings for a specific type to 0."""
    sql = "DELETE FROM user_warnings WHERE chat_id = %s AND user_id = %s AND warn_type = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, user_id, warn_type))
            conn.commit()
    except Exception as e:
        logger.error(f"Error in reset_user_warnings: {e}")
        conn.rollback()
    finally:
        conn.close()
