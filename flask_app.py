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
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

# Initialize DB and populate with default user
def init_db():
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Create tables if they don't exist
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
        
        # Check if default HOD exists, if not, create one
        cursor.execute("SELECT * FROM hods WHERE username = 'admin'")
        if cursor.fetchone() is None:
            hashed_password = generate_password_hash("password")
            cursor.execute("INSERT INTO hods (username, password) VALUES (%s, %s)", ('admin', hashed_password))
            print("Default HOD 'admin' created.")
            
        conn.commit()
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Initial database setup
init_db()

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
        # Check HODs table
        cursor.execute("SELECT * FROM hods WHERE username = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            return jsonify({'username': user['username'], 'role': 'HOD'})
        
        # Check Engineers table
        cursor.execute("SELECT * FROM engineers WHERE name = %s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            return jsonify({'username': user['name'], 'role': 'Engineer'})
            
        return jsonify({'message': 'Invalid credentials'}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'message': 'An error occurred during login'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/hods', methods=['POST'])
def add_hod():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username and password are required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO hods (username, password) VALUES (%s, %s) RETURNING *", (username, hashed_password))
        new_hod = cursor.fetchone()
        conn.commit()
        return jsonify(new_hod), 201
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'message': 'Username already exists'}), 409
    except Exception as e:
        print(f"Error adding HOD: {e}")
        conn.rollback()
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/engineers', methods=['GET', 'POST', 'DELETE'])
def manage_engineers():
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if request.method == 'GET':
            cursor.execute("SELECT id, name FROM engineers")
            engineers = cursor.fetchall()
            return jsonify(engineers)
            
        elif request.method == 'POST':
            data = request.json
            name = data.get('name')
            password = data.get('password')
            if not name or not password:
                return jsonify({'message': 'Name and password required'}), 400
            
            hashed_password = generate_password_hash(password)
            cursor.execute("INSERT INTO engineers (name, password) VALUES (%s, %s) RETURNING *", (name, hashed_password))
            new_engineer = cursor.fetchone()
            conn.commit()
            return jsonify(new_engineer), 201
            
        elif request.method == 'DELETE':
            data = request.json
            name = data.get('name')
            if not name:
                return jsonify({'message': 'Name required'}), 400
            
            cursor.execute("DELETE FROM engineers WHERE name=%s RETURNING *", (name,))
            deleted_engineer = cursor.fetchone()
            if deleted_engineer:
                conn.commit()
                return jsonify({'message': 'Engineer deleted', 'engineer': deleted_engineer}), 200
            else:
                conn.rollback()
                return jsonify({'message': 'Engineer not found'}), 404
                
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'message': 'Name already exists'}), 409
    except Exception as e:
        print(f"Error managing engineers: {e}")
        conn.rollback()
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/stocks', methods=['GET', 'POST', 'DELETE'])
def manage_stocks():
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if request.method == 'GET':
            cursor.execute("SELECT * FROM stocks")
            stocks = cursor.fetchall()
            return jsonify(stocks)
            
        elif request.method == 'POST':
            data = request.json
            name = data.get('name')
            quantity = data.get('quantity')
            if not name or quantity is None or not isinstance(quantity, int) or quantity < 0:
                return jsonify({'message': 'Name and positive integer quantity required'}), 400
            
            cursor.execute("INSERT INTO stocks (name, quantity) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET quantity = stocks.quantity + EXCLUDED.quantity RETURNING *", (name, quantity))
            updated_stock = cursor.fetchone()
            conn.commit()
            return jsonify(updated_stock), 201
            
        elif request.method == 'DELETE':
            data = request.json
            name = data.get('name')
            if not name:
                return jsonify({'message': 'Name required'}), 400
            
            cursor.execute("DELETE FROM stocks WHERE name=%s RETURNING *", (name,))
            deleted_stock = cursor.fetchone()
            if deleted_stock:
                conn.commit()
                return jsonify({'message': 'Stock deleted', 'stock': deleted_stock}), 200
            else:
                conn.rollback()
                return jsonify({'message': 'Stock not found'}), 404
                
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({'message': 'Stock name already exists'}), 409
    except Exception as e:
        print(f"Error managing stocks: {e}")
        conn.rollback()
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/requests', methods=['GET', 'POST'])
def manage_requests():
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        if request.method == 'GET':
            cursor.execute("SELECT * FROM requests ORDER BY requested_at DESC")
            requests = cursor.fetchall()
            return jsonify(requests)
            
        elif request.method == 'POST':
            data = request.json
            engineer_name = data.get('engineerName')
            stock_name = data.get('stockName')
            quantity = data.get('quantity')
            
            if not all([engineer_name, stock_name, quantity]):
                return jsonify({'message': 'Missing data'}), 400
            
            cursor.execute("INSERT INTO requests (engineer_name, stock_name, quantity, status) VALUES (%s, %s, %s, 'Pending') RETURNING *", (engineer_name, stock_name, quantity))
            new_request = cursor.fetchone()
            conn.commit()
            return jsonify(new_request), 201

    except Exception as e:
        print(f"Error managing requests: {e}")
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
                
            if status == 'Received':
                stock_name = req['stock_name']
                qty = req['quantity']
                
                cursor.execute("SELECT * FROM stocks WHERE name=%s", (stock_name,))
                stock = cursor.fetchone()
                if stock and stock['quantity'] >= qty:
                    cursor.execute("UPDATE stocks SET quantity=quantity-%s WHERE name=%s", (qty, stock_name))
                    cursor.execute("UPDATE requests SET status='Completed', received_at=CURRENT_TIMESTAMP WHERE id=%s", (id,))
                    cursor.execute("INSERT INTO usage_log (engineer_name, stock_name, quantity) VALUES (%s, %s, %s)", (req['engineer_name'], stock_name, qty))
                else:
                    return jsonify({'message': 'Not enough stock'}), 400
                    
            elif status == 'Sent':
                cursor.execute("UPDATE requests SET status='Sent', sent_at=CURRENT_TIMESTAMP WHERE id=%s", (id,))
            elif status in ['Accepted', 'Denied']:
                cursor.execute("UPDATE requests SET status=%s WHERE id=%s", (status, id))
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

@app.route('/api/usage_log', methods=['GET'])
def get_usage_log():
    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database connection error'}), 500
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT * FROM usage_log ORDER BY used_at DESC")
        logs = cursor.fetchall()
        return jsonify(logs)
    except Exception as e:
        print(f"Error getting usage log: {e}")
        return jsonify({'message': 'An error occurred'}), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
