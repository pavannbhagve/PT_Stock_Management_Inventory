import os
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Database Connection ---
def get_db_connection():
    """Establishes and returns a database connection using the DATABASE_URL."""
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable is not set.")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("Successfully connected to the database.")
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

# --- Database Initialization ---
def init_db():
    """Initializes the database by creating all necessary tables."""
    conn = get_db_connection()
    if not conn:
        print("Cannot initialize database without a connection.")
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Create tables for HODs, Engineers, and their interactions
        print("Creating database tables if they do not exist...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hods (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engineers (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                quantity INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                engineer_name TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                status TEXT NOT NULL,
                requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP WITH TIME ZONE,
                received_at TIMESTAMP WITH TIME ZONE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_log (
                id SERIAL PRIMARY KEY,
                engineer_name TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                used_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default HOD user if one does not already exist
        print("Checking for default 'admin' user...")
        cursor.execute("SELECT * FROM hods WHERE username = 'admin'")
        if cursor.fetchone() is None:
            hashed_password = generate_password_hash("password")
            cursor.execute("INSERT INTO hods (username, password) VALUES (%s, %s)", ('admin', hashed_password))
            print("Default HOD 'admin' created successfully.")
            
        conn.commit()
        print("Database initialization complete.")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    init_db()
