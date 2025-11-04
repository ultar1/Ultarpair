import psycopg2
import logging
from config import DATABASE_URL

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
    """Initializes the database and creates the blacklist table if it doesn't exist."""
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to get DB connection in init_db.")
        return
        
    try:
        with conn.cursor() as cur:
            # --- FIX: Added chat_id column and made (term, chat_id) unique ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    term TEXT NOT NULL,
                    UNIQUE(term, chat_id)
                );
            """)
            conn.commit()
            logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        conn.close()

def add_to_blacklist(chat_id: int, term: str) -> bool:
    """Adds a term to the blacklist for a specific chat.
       Returns True on success, False if it exists.
    """
    # --- FIX: Added chat_id to the SQL query ---
    sql = """
        INSERT INTO blacklist (chat_id, term) 
        VALUES (%s, %s) 
        ON CONFLICT (term, chat_id) DO NOTHING
    """
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, term.lower()))
            conn.commit()
            # rowcount will be 1 if inserted, 0 if conflict (already exists)
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error adding to blacklist for chat {chat_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def remove_from_blacklist(chat_id: int, term: str) -> bool:
    """Removes a term from the blacklist for a specific chat.
       Returns True on success, False if not found.
    """
    # --- FIX: Added chat_id to the SQL query ---
    sql = "DELETE FROM blacklist WHERE chat_id = %s AND term = %s"
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id, term.lower()))
            conn.commit()
            # rowcount will be 1 if deleted, 0 if not found
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing from blacklist for chat {chat_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_blacklist(chat_id: int) -> set:
    """Gets the blacklist for a specific chat and returns it as a set."""
    # --- FIX: Added chat_id to the SQL query ---
    sql = "SELECT term FROM blacklist WHERE chat_id = %s"
    conn = get_db_connection()
    if not conn:
        return set()
        
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (chat_id,))
            # Fetch all rows, unpack the first element from each tuple (term,)
            results = {row[0] for row in cur.fetchall()}
            return results
    except Exception as e:
        logger.error(f"Error getting blacklist for chat {chat_id}: {e}")
        return set() # Return an empty set on error
    finally:
        conn.close()
