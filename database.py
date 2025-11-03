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
    cur = conn.cursor()
    
    # Create the table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id SERIAL PRIMARY KEY,
            term TEXT UNIQUE NOT NULL
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def add_to_blacklist(term: str) -> bool:
    """Adds a term to the blacklist. Returns True on success, False if it exists."""
    sql = "INSERT INTO blacklist (term) VALUES (%s) ON CONFLICT (term) DO NOTHING"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (term.lower(),))
            conn.commit()
            # rowcount will be 1 if inserted, 0 if conflict (already exists)
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error adding to blacklist: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def remove_from_blacklist(term: str) -> bool:
    """Removes a term from the blacklist. Returns True on success, False if not found."""
    sql = "DELETE FROM blacklist WHERE term = %s"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (term.lower(),))
            conn.commit()
            # rowcount will be 1 if deleted, 0 if not found
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error removing from blacklist: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_blacklist() -> set:
    """Gets the entire blacklist from the database and returns it as a set."""
    sql = "SELECT term FROM blacklist"
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            # Fetch all rows, unpack the first element from each tuple (term,)
            results = {row[0] for row in cur.fetchall()}
            return results
    except Exception as e:
        logger.error(f"Error getting blacklist: {e}")
        return set() # Return an empty set on error
    finally:
        conn.close()
