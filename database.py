import psycopg2
import logging
import psycopg2.extras # <-- Import this for dictionary cursors
from config import DATABASE_URL

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establishes a connection to the database."""
    try:
        # Use a dictionary cursor to get results as dicts
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.DictCursor
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Blacklist table (unchanged)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    id SERIAL PRIMARY KEY,
                    term TEXT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    UNIQUE(term, chat_id)
                );
            """)
            
            # --- (NEW) Job scheduling table ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    id SERIAL PRIMARY KEY,
                    job_type TEXT NOT NULL,          -- e.g., 'unmute', 'unpin'
                    chat_id BIGINT NOT NULL,
                    target_id BIGINT NOT NULL,       -- user_id for unmute, message_id for unpin
                    run_at TIMESTAMPTZ NOT NULL      -- 'timestamp with time zone'
                );
            """)

                # ... inside init_db() ...
    
    # NEW: Table to store per-group settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id BIGINT PRIMARY KEY,
            antibot_enabled BOOLEAN DEFAULT FALSE
        );
    """)
    
    # ... your other tables ...

            # Create an index for faster job polling
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_run_at ON scheduled_jobs (run_at);
            """)
            
            conn.commit()
            logger.info("Database tables initialized/verified.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
    finally:
        cur.close()
        conn.close()

# --- Blacklist Functions (Unchanged) ---

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

def set_antibot_status(chat_id: int, enabled: bool) -> bool:
    """Sets the anti-bot status for a group. Returns True on success."""
    # This query will insert if not present, or update if it is.
    sql = """
        INSERT INTO group_settings (chat_id, antibot_enabled)
        VALUES (%s, %s)
        ON CONFLICT (chat_id)
        DO UPDATE SET antibot_enabled = EXCLUDED.antibot_enabled;
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, enabled))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error setting anti-bot status: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def is_antibot_enabled(chat_id: int) -> bool:
    """Checks if the anti-bot feature is enabled for a group. Defaults to False."""
    sql = "SELECT antibot_enabled FROM group_settings WHERE chat_id = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id,))
            result = cur.fetchone()
            # If 'result' is not None and result[0] is True
            if result and result[0]:
                return True
            return False # Default to false if no row exists or it's false
    except Exception as e:
        logger.error(f"Error checking anti-bot status: {e}")
        return False # Default to false on error
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
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id,))
            results = {row[0] for row in cur.fetchall()}
            return results
    except Exception as e:
        logger.error(f"Error getting blacklist: {e}")
        return set()
    finally:
        conn.close()

# --- (NEW) Job Functions ---

def add_job(job_type: str, chat_id: int, target_id: int, run_at: 'datetime') -> bool:
    """Adds a new job to the database."""
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
    """
    Gets all jobs that are due to run.
    Uses 'FOR UPDATE SKIP LOCKED' to prevent multiple workers from
    grabbing the same job.
    """
    sql = "SELECT * FROM scheduled_jobs WHERE run_at <= NOW() ORDER BY run_at FOR UPDATE SKIP LOCKED"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            jobs = cur.fetchall()
            conn.commit() # Commit to release the lock on selected rows
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
