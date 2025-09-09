import os
import datetime
from flask import Flask, jsonify, request, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
# Use the External Database URL for Render deployment
DATABASE_URL = "postgresql://stock_db_01nd_user:jgwJcLia0lAEYlNBmMUCAlKBs4Z7cSsd@dpg-d2vt6bodl3ps739i4brg-a.oregon-postgres.render.com/stock_db_01nd"
SECRET_KEY = os.getenv("SECRET_KEY", "secret")

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# PostgreSQL connection
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Database connection failed: {e}")
        return None

# Initialize DB - This function should only be run ONCE to set up the database schema.
def init_db():
    print("Initializing database...")
    conn = get_db_connection()
    if conn is None:
        print("Could not connect to database, skipping initialization.")
        return
    cursor = conn.cursor()
    
    # Create tables with all necessary columns
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
            quantity INTEGER NOT NULL,
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            requester_name TEXT NOT NULL,
            remarks TEXT,
            status TEXT NOT NULL,
            is_urgent BOOLEAN DEFAULT FALSE,
            docket_number TEXT,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            accepted_timestamp TIMESTAMP WITH TIME ZONE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS engineer_personal_stock (
            id SERIAL PRIMARY KEY,
            engineer_name TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_usage_log (
            id SERIAL PRIMARY KEY,
            engineer_name TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            site_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            amc_cmc TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add default HOD if not exists
    cursor.execute("SELECT * FROM hods WHERE username='HOD'")
    if cursor.fetchone() is None:
        hashed_password = generate_password_hash('password123')
        cursor.execute("INSERT INTO hods (username, password) VALUES (%s, %s)", ('HOD', hashed_password))
    
    # Add default engineer if not exists
    cursor.execute("SELECT * FROM engineers WHERE name='Eng-Alice'")
    if cursor.fetchone() is None:
        hashed_password = generate_password_hash('password')
        cursor.execute("INSERT INTO engineers (name, password) VALUES (%s, %s)", ('Eng-Alice', hashed_password))

    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialization complete.")

# Helper function to convert DB data to JSON serializable format
def format_data(data):
    if isinstance(data, list):
        for item in data:
            for key, value in item.items():
                if isinstance(value, datetime.datetime):
                    item[key] = value.isoformat()
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime.datetime):
                data[key] = value.isoformat()
    return data

# --- Routes ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM hods WHERE username=%s", (username,))
    hod = cursor.fetchone()
    if hod and check_password_hash(hod['password'], password):
        cursor.close()
        conn.close()
        return jsonify({'role':'HOD','name':'HOD', 'message':'HOD login successful'})
    
    cursor.execute("SELECT * FROM engineers WHERE name=%s", (username,))
    eng = cursor.fetchone()
    if eng and check_password_hash(eng['password'], password):
        cursor.close()
        conn.close()
        return jsonify({'role':'Engineer','name': eng['name'], 'message':'Engineer login successful'})
    
    cursor.close()
    conn.close()
    return jsonify({'message':'Invalid credentials'}), 401

# Engineer Management
@app.route('/api/engineers', methods=['GET','POST'])
def engineers():
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    if request.method=='GET':
        cursor.execute("SELECT id, name FROM engineers ORDER BY name")
        engineers = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(engineers)
    else:
        data = request.json
        name = data.get('name')
        password = generate_password_hash(data.get('password'))
        try:
            cursor.execute("INSERT INTO engineers (name, password) VALUES (%s,%s)", (name,password))
            conn.commit()
            return jsonify({'message':'Engineer added'}), 201
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({'message':'Engineer username already exists'}), 409
        finally:
            cursor.close()
            conn.close()

@app.route('/api/engineers/<int:id>', methods=['DELETE'])
def delete_engineer(id):
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    cursor.execute("DELETE FROM engineers WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message':'Engineer deleted'})

# Main Stock Management
@app.route('/api/stocks', methods=['GET','POST'])
def stocks():
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    
    if request.method=='GET':
        cursor.execute("SELECT * FROM stocks ORDER BY name")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(format_data(data))
    
    elif request.method=='POST':
        data = request.json
        name = data.get('name')
        quantity = data.get('quantity')
        
        cursor.execute("SELECT * FROM stocks WHERE name=%s", (name,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE stocks SET quantity=quantity+%s, last_updated=CURRENT_TIMESTAMP WHERE name=%s", (quantity, name))
        else:
            cursor.execute("INSERT INTO stocks (name, quantity) VALUES (%s,%s)", (name, quantity))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Stock updated'}), 201

# This endpoint handles both name and quantity edits for a specific stock ID
@app.route('/api/stocks/<int:id>', methods=['PUT', 'DELETE'])
def manage_stock_by_id(id):
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    
    if request.method == 'PUT':
        data = request.json
        new_name = data.get('name')
        new_quantity = data.get('quantity')
        
        updates = []
        params = []
        if new_name:
            updates.append("name=%s")
            params.append(new_name)
        if new_quantity is not None:
            updates.append("quantity=%s")
            params.append(new_quantity)
        
        if updates:
            updates.append("last_updated=CURRENT_TIMESTAMP")
            params.append(id)
            query = f"UPDATE stocks SET {', '.join(updates)} WHERE id=%s"
            cursor.execute(query, tuple(params))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'message':'Stock updated successfully'})
        
        cursor.close()
        conn.close()
        return jsonify({'message':'No valid fields to update'}), 400

    elif request.method == 'DELETE':
        cursor.execute("DELETE FROM stocks WHERE id=%s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Stock deleted'})

# Requests Management
@app.route('/api/requests', methods=['GET', 'POST'])
def requests_list():
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute("SELECT * FROM requests ORDER BY timestamp DESC")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(format_data(data))
    else:
        data = request.json
        stock_name = data['stock_name']
        quantity = data['quantity']
        requester_name = data['requester_name']
        remarks = data.get('remarks')
        is_urgent = data.get('is_urgent', False)
        
        cursor.execute("INSERT INTO requests (stock_name, quantity, requester_name, remarks, status, is_urgent) VALUES (%s, %s, %s, %s, %s, %s)",
                       (stock_name, quantity, requester_name, remarks, 'Pending', is_urgent))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Request submitted'}), 201

@app.route('/api/requests/<int:id>', methods=['PUT', 'DELETE'])
def manage_request_by_id(id):
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()

    if request.method == 'PUT':
        data = request.json
        
        if 'status' in data: # Status update (Accept, Deny, Mark Received, Send)
            status = data['status']
            docket_number = data.get('docket_number')
            
            cursor.execute("SELECT * FROM requests WHERE id=%s", (id,))
            req = cursor.fetchone()
            if not req:
                return jsonify({'message':'Request not found'}), 404
            
            if status == 'In Transit':
                cursor.execute("UPDATE requests SET status=%s, docket_number=%s, accepted_timestamp=CURRENT_TIMESTAMP WHERE id=%s", ('In Transit', docket_number, id))
                
            elif status == 'Completed':
                stock_name = req['stock_name']
                qty = req['quantity']
                requester_name = req['requester_name']
                
                cursor.execute("SELECT * FROM stocks WHERE name=%s", (stock_name,))
                main_stock = cursor.fetchone()
                
                if not main_stock or main_stock['quantity'] < qty:
                    conn.rollback()
                    return jsonify({'message':'Not enough stock in main inventory'}), 400
                
                cursor.execute("UPDATE stocks SET quantity=quantity-%s, last_updated=CURRENT_TIMESTAMP WHERE name=%s", (qty, stock_name))
                
                cursor.execute("SELECT * FROM engineer_personal_stock WHERE engineer_name=%s AND stock_name=%s", (requester_name, stock_name))
                personal_item = cursor.fetchone()
                if personal_item:
                    cursor.execute("UPDATE engineer_personal_stock SET quantity=quantity+%s, last_updated=CURRENT_TIMESTAMP WHERE engineer_name=%s AND stock_name=%s",
                                   (qty, requester_name, stock_name))
                else:
                    cursor.execute("INSERT INTO engineer_personal_stock (engineer_name, stock_name, quantity) VALUES (%s, %s, %s)",
                                   (requester_name, stock_name, qty))

                cursor.execute("UPDATE requests SET status=%s WHERE id=%s", ('Completed', id))

            elif status == 'Rejected':
                cursor.execute("UPDATE requests SET status=%s WHERE id=%s", (status, id))

            else:
                return jsonify({'message':'Invalid status update'}), 400
            
            conn.commit()
            return jsonify({'message':'Request updated successfully'}), 200

        else: # Edit request details
            stock_name = data.get('stock_name')
            quantity = data.get('quantity')
            remarks = data.get('remarks')
            
            updates = []
            params = []
            if stock_name:
                updates.append("stock_name=%s")
                params.append(stock_name)
            if quantity is not None:
                updates.append("quantity=%s")
                params.append(quantity)
            if remarks:
                updates.append("remarks=%s")
                params.append(remarks)
            
            if updates:
                params.append(id)
                query = f"UPDATE requests SET {', '.join(updates)} WHERE id=%s"
                cursor.execute(query, tuple(params))
                conn.commit()
                cursor.close()
                conn.close()
                return jsonify({'message':'Request edited successfully'})
            
            cursor.close()
            conn.close()
            return jsonify({'message':'No valid fields to update'}), 400

    elif request.method == 'DELETE':
        cursor.execute("DELETE FROM requests WHERE id=%s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Request deleted'})

# Engineer Personal Stock
@app.route('/api/personal_stock', methods=['GET', 'POST'])
def personal_stock():
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    if request.method == 'GET':
        engineer_name = request.args.get('engineer_name')
        if not engineer_name:
            return jsonify({'message': 'Engineer name is required'}), 400
        cursor.execute("SELECT * FROM engineer_personal_stock WHERE engineer_name=%s", (engineer_name,))
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(format_data(data))
    
    elif request.method == 'POST':
        data = request.json
        engineer_name = data['engineer_name']
        stock_name = data['stock_name']
        quantity = data['quantity']
        
        cursor.execute("SELECT * FROM engineer_personal_stock WHERE engineer_name=%s AND stock_name=%s", (engineer_name, stock_name))
        existing_stock = cursor.fetchone()
        
        if existing_stock:
            cursor.execute("UPDATE engineer_personal_stock SET quantity=quantity+%s, last_updated=CURRENT_TIMESTAMP WHERE engineer_name=%s AND stock_name=%s",
                           (quantity, engineer_name, stock_name))
        else:
            cursor.execute("INSERT INTO engineer_personal_stock (engineer_name, stock_name, quantity) VALUES (%s, %s, %s)",
                           (engineer_name, stock_name, quantity))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message': 'Personal stock updated'}), 201

# Usage Log
@app.route('/api/usage_log', methods=['GET', 'POST'])
def usage_log():
    conn = get_db_connection()
    if not conn: return jsonify({'message':'Database connection error'}), 500
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute("SELECT * FROM stock_usage_log ORDER BY timestamp DESC")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(format_data(data))
    elif request.method == 'POST':
        data = request.json
        engineer_name = data['engineer_name']
        stock_name = data['stock_name']
        quantity = data['quantity']
        site_name = data['site_name']
        reason = data['reason']
        amc_cmc = data['amc_cmc']
        
        # Deduct from personal stock
        cursor.execute("SELECT * FROM engineer_personal_stock WHERE engineer_name=%s AND stock_name=%s", (engineer_name, stock_name))
        personal_stock = cursor.fetchone()
        
        if not personal_stock or personal_stock['quantity'] < quantity:
            cursor.close()
            conn.close()
            return jsonify({'message': 'Not enough stock in personal inventory'}), 400
        
        cursor.execute("UPDATE engineer_personal_stock SET quantity=quantity-%s, last_updated=CURRENT_TIMESTAMP WHERE engineer_name=%s AND stock_name=%s",
                       (quantity, engineer_name, stock_name))
                        
        # Add to usage log
        cursor.execute("INSERT INTO stock_usage_log (engineer_name, stock_name, quantity, site_name, reason, amc_cmc) VALUES (%s, %s, %s, %s, %s, %s)",
                       (engineer_name, stock_name, quantity, site_name, reason, amc_cmc))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Usage log entry created'}), 201


if __name__ == '__main__':
    # Only run init_db() on initial setup, not on every app start.
    # For Render, you would run this manually from the shell.
    # init_db() 
    app.run(debug=True)
