import os
from flask import Flask, jsonify, request, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# PostgreSQL connection
def get_db_connection():
    """Establishes and returns a database connection using the DATABASE_URL."""
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable is not set.")
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

# Initialize DB and populate with a default user
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Check HODs table first
        cursor.execute("SELECT * FROM hods WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            return jsonify({'message': 'Login successful', 'role': 'HOD', 'username': user['username']}), 200

        # Check Engineers table
        cursor.execute("SELECT * FROM engineers WHERE name = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            return jsonify({'message': 'Login successful', 'role': 'Engineer', 'username': user['name']}), 200

        return jsonify({'message': 'Invalid credentials'}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

# --- API Endpoints for Requests ---
@app.route('/api/requests', methods=['POST', 'GET'])
def handle_requests():
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.json
            engineer_name = data.get('engineer_name')
            stock_name = data.get('stock_name')
            quantity = data.get('quantity')
            status = 'Awaiting Approval'

            if not all([engineer_name, stock_name, quantity]):
                return jsonify({'message': 'Missing data'}), 400

            cursor.execute(
                "INSERT INTO requests (engineer_name, stock_name, quantity, status) VALUES (%s, %s, %s, %s)",
                (engineer_name, stock_name, quantity, status)
            )
            conn.commit()
            return jsonify({'message': 'Request submitted successfully'}), 201

        elif request.method == 'GET':
            cursor.execute("SELECT * FROM requests ORDER BY requested_at DESC")
            requests = cursor.fetchall()
            return jsonify(requests)
    except Exception as e:
        print(f"Error handling requests: {e}")
        conn.rollback()
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/requests/<int:id>', methods=['PUT', 'DELETE'])
def update_request(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        if request.method == 'PUT':
            data = request.json
            status = data.get('status')
            
            cursor.execute("SELECT * FROM requests WHERE id=%s", (id,))
            req = cursor.fetchone()
            if not req:
                return jsonify({'message': 'Request not found'}), 404
            
            if status == 'Accepted':
                cursor.execute("UPDATE requests SET status=%s, sent_at=CURRENT_TIMESTAMP WHERE id=%s", (status, id))
            elif status == 'Denied':
                cursor.execute("UPDATE requests SET status=%s WHERE id=%s", (status, id))
            elif status == 'Received':
                cursor.execute(
                    "UPDATE requests SET status=%s, received_at=CURRENT_TIMESTAMP WHERE id=%s",
                    ('Completed', id)
                )
            else:
                return jsonify({'message': 'Invalid status'}), 400
                
            conn.commit()
            return jsonify({'message': 'Request updated successfully'}), 200
            
        elif request.method == 'DELETE':
            cursor.execute("DELETE FROM requests WHERE id=%s RETURNING *", (id,))
            deleted_request = cursor.fetchone()
            if deleted_request:
                conn.commit()
                return jsonify({'message': 'Request deleted'}), 200
            else:
                conn.rollback()
                return jsonify({'message': 'Request not found'}), 404

    except Exception as e:
        print(f"Error updating request: {e}")
        conn.rollback()
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/usage_log', methods=['POST', 'GET'])
def handle_usage_log():
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if request.method == 'POST':
            data = request.json
            engineer_name = data.get('engineer_name')
            stock_name = data.get('stock_name')
            quantity = data.get('quantity')
            
            if not all([engineer_name, stock_name, quantity]):
                return jsonify({'message': 'Missing data'}), 400

            cursor.execute(
                "INSERT INTO usage_log (engineer_name, stock_name, quantity) VALUES (%s, %s, %s)",
                (engineer_name, stock_name, quantity)
            )
            conn.commit()
            return jsonify({'message': 'Usage log added successfully'}), 201

        elif request.method == 'GET':
            cursor.execute("SELECT * FROM usage_log ORDER BY used_at DESC")
            logs = cursor.fetchall()
            return jsonify(logs)
    except Exception as e:
        print(f"Error handling usage log: {e}")
        conn.rollback()
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    # Call the database initialization function here for local development.
    # It is safe to run multiple times because of the "IF NOT EXISTS" clauses.
    init_db()
    app.run(debug=True)
