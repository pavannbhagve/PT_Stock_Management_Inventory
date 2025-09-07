import os
import sqlite3
from flask import Flask, jsonify, request, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

# This single file contains all the necessary code and replaces your old flask_app.py and database_db.py.

# Initialize Flask app
app = Flask(__name__)

# Correctly set the database path
# This ensures the database is created and found in the same directory as the script.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hods (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS engineers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            quantity INTEGER NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY,
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            requester_name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    ''')
    
    # Populate HOD if it doesn't exist
    cursor.execute('SELECT COUNT(*) FROM hods')
    if cursor.fetchone()[0] == 0:
        hashed_password = generate_password_hash('password')
        cursor.execute("INSERT INTO hods (username, password) VALUES (?, ?)", ('HOD', hashed_password))
    
    conn.commit()
    conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    """Handles user login for HOD and Engineer roles."""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    
    # Check for HOD login
    hod = conn.execute("SELECT * FROM hods WHERE username = ?", (username,)).fetchone()
    if hod and check_password_hash(hod['password'], password):
        conn.close()
        return jsonify({'role': 'HOD', 'message': 'HOD login successful'})
        
    # Check for Engineer login
    engineer = conn.execute("SELECT * FROM engineers WHERE name = ?", (username,)).fetchone()
    if engineer and check_password_hash(engineer['password'], password):
        conn.close()
        return jsonify({'role': 'Engineer', 'name': engineer['name'], 'message': 'Engineer login successful'})
    
    conn.close()
    return jsonify({'message': 'Invalid credentials'}), 401

# HOD - Engineer Management
@app.route('/api/engineers', methods=['GET', 'POST'])
def manage_engineers():
    conn = get_db_connection()
    if request.method == 'GET':
        engineers = conn.execute("SELECT * FROM engineers").fetchall()
        conn.close()
        return jsonify([dict(row) for row in engineers])
    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        password = data.get('password')
        hashed_password = generate_password_hash(password)
        conn.execute("INSERT INTO engineers (name, password) VALUES (?, ?)", (name, hashed_password))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Engineer added'}), 201

@app.route('/api/engineers/<int:engineer_id>', methods=['DELETE'])
def delete_engineer(engineer_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM engineers WHERE id = ?", (engineer_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Engineer deleted'})

# HOD - Stock Management
@app.route('/api/stocks', methods=['GET', 'POST', 'PUT'])
def manage_stocks():
    conn = get_db_connection()
    if request.method == 'GET':
        stocks = conn.execute("SELECT * FROM stocks").fetchall()
        conn.close()
        return jsonify([dict(row) for row in stocks])
    elif request.method == 'POST':
        data = request.json
        stock_name = data.get('name')
        quantity = data.get('quantity')
        
        existing_stock = conn.execute("SELECT * FROM stocks WHERE name = ?", (stock_name,)).fetchone()
        
        if existing_stock:
            conn.execute("UPDATE stocks SET quantity = quantity + ? WHERE name = ?", (quantity, stock_name))
        else:
            conn.execute("INSERT INTO stocks (name, quantity) VALUES (?, ?)", (stock_name, quantity))
        
        conn.commit()
        conn.close()
        return jsonify({'message': 'Stock updated'}), 201
    elif request.method == 'PUT':
        data = request.json
        stock_name = data.get('name')
        quantity = data.get('quantity')
        
        existing_stock = conn.execute("SELECT * FROM stocks WHERE name = ?", (stock_name,)).fetchone()
        if existing_stock:
            conn.execute("UPDATE stocks SET quantity = ? WHERE name = ?", (quantity, stock_name))
            conn.commit()
            conn.close()
            return jsonify({'message': 'Stock quantity set successfully'}), 200
        else:
            conn.close()
            return jsonify({'message': 'Stock not found'}), 404

@app.route('/api/stocks/<int:stock_id>', methods=['DELETE'])
def delete_stock(stock_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM stocks WHERE id = ?", (stock_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Stock deleted'})

# HOD & Engineer - Request Management
@app.route('/api/requests', methods=['GET', 'POST'])
def manage_requests():
    conn = get_db_connection()
    if request.method == 'GET':
        requests_list = conn.execute("SELECT * FROM requests").fetchall()
        conn.close()
        return jsonify([dict(row) for row in requests_list])
    elif request.method == 'POST':
        data = request.json
        conn.execute("INSERT INTO requests (stock_name, quantity, requester_name, status) VALUES (?, ?, ?, ?)",
                      (data['stock_name'], data['quantity'], data['requester_name'], 'Pending'))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Request submitted'}), 201

@app.route('/api/requests/<int:request_id>', methods=['PUT'])
def update_request(request_id):
    request_data = request.json
    status = request_data.get('status')
    
    conn = get_db_connection()
    cursor = conn.cursor()

    req_to_update = cursor.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    
    if req_to_update:
        if status == 'Received':
            stock_name = req_to_update['stock_name']
            requested_quantity = req_to_update['quantity']
            
            stock_item = cursor.execute("SELECT * FROM stocks WHERE name = ?", (stock_name,)).fetchone()

            if stock_item:
                if stock_item['quantity'] >= requested_quantity:
                    cursor.execute("UPDATE stocks SET quantity = quantity - ? WHERE name = ?", (requested_quantity, stock_name))
                    cursor.execute("UPDATE requests SET status = ? WHERE id = ?", ('Completed', request_id))
                    conn.commit()
                    conn.close()
                    return jsonify({'message': 'Request marked as completed and stock updated.'}), 200
                else:
                    conn.close()
                    return jsonify({'message': 'Not enough stock to fulfill this request.'}), 400
            else:
                conn.close()
                return jsonify({'message': 'Stock item not found.'}), 404
        
        elif status == 'Accepted':
            cursor.execute("UPDATE requests SET status = ? WHERE id = ?", ('Accepted', request_id))
            conn.commit()
            conn.close()
            return jsonify({'message': 'Request accepted.'}), 200
        
        elif status == 'Denied':
            cursor.execute("UPDATE requests SET status = ? WHERE id = ?", ('Denied', request_id))
            conn.commit()
            conn.close()
            return jsonify({'message': 'Request denied.'}), 200
        
        else:
            conn.close()
            return jsonify({'message': 'Invalid status provided.'}), 400
    
    conn.close()
    return jsonify({'message': 'Request not found'}), 404

# The home route now serves a static template
@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    # Initialize the database on startup
    init_db()
    app.run(debug=True)
