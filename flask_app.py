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
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

# Initialize DB
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            requester_name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)
    
    # Add default HOD if not exists
    cursor.execute("SELECT * FROM hods WHERE username='HOD'")
    if cursor.fetchone() is None:
        hashed_password = generate_password_hash('password')
        cursor.execute("INSERT INTO hods (username, password) VALUES (%s, %s)", ('HOD', hashed_password))
    
    conn.commit()
    cursor.close()
    conn.close()

# --- Routes ---

@app.route('/')
def home():
    return render_template('index.html')

# Login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # HOD login
    cursor.execute("SELECT * FROM hods WHERE username=%s", (username,))
    hod = cursor.fetchone()
    if hod and check_password_hash(hod['password'], password):
        cursor.close()
        conn.close()
        return jsonify({'role':'HOD','message':'HOD login successful'})
    
    # Engineer login
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
    cursor = conn.cursor()
    if request.method=='GET':
        cursor.execute("SELECT id, name FROM engineers")
        engineers = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(engineers)
    else:
        data = request.json
        name = data.get('name')
        password = generate_password_hash(data.get('password'))
        cursor.execute("INSERT INTO engineers (name, password) VALUES (%s,%s)", (name,password))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Engineer added'}), 201

@app.route('/api/engineers/<int:id>', methods=['DELETE'])
def delete_engineer(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM engineers WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message':'Engineer deleted'})

# Stock Management
@app.route('/api/stocks', methods=['GET','POST','PUT'])
def stocks():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method=='GET':
        cursor.execute("SELECT * FROM stocks")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(data)
    
    elif request.method=='POST':  # Add / increase stock
        data = request.json
        name = data.get('name')
        quantity = data.get('quantity')
        
        cursor.execute("SELECT * FROM stocks WHERE name=%s", (name,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("UPDATE stocks SET quantity=quantity+%s WHERE name=%s",(quantity,name))
        else:
            cursor.execute("INSERT INTO stocks (name, quantity) VALUES (%s,%s)", (name, quantity))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Stock updated'}), 201
    
    elif request.method=='PUT':  # Set stock quantity
        data = request.json
        name = data.get('name')
        quantity = data.get('quantity')
        cursor.execute("UPDATE stocks SET quantity=%s WHERE name=%s", (quantity,name))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Stock quantity set'})

# Delete stock
@app.route('/api/stocks/<int:id>', methods=['DELETE'])
def delete_stock(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stocks WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message':'Stock deleted'})

# Requests
@app.route('/api/requests', methods=['GET','POST'])
def requests_list():
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method=='GET':
        cursor.execute("SELECT * FROM requests")
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(data)
    else:
        data = request.json
        cursor.execute("INSERT INTO requests (stock_name, quantity, requester_name, status) VALUES (%s,%s,%s,%s)",
                       (data['stock_name'], data['quantity'], data['requester_name'], 'Pending'))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'message':'Request submitted'}), 201

@app.route('/api/requests/<int:id>', methods=['PUT'])
def update_request(id):
    data = request.json
    status = data.get('status')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM requests WHERE id=%s", (id,))
    req = cursor.fetchone()
    if not req:
        cursor.close()
        conn.close()
        return jsonify({'message':'Request not found'}), 404
    
    if status=='Received':
        stock_name = req['stock_name']
        qty = req['quantity']
        cursor.execute("SELECT * FROM stocks WHERE name=%s", (stock_name,))
        stock = cursor.fetchone()
        if stock and stock['quantity']>=qty:
            cursor.execute("UPDATE stocks SET quantity=quantity-%s WHERE name=%s",(qty,stock_name))
            cursor.execute("UPDATE requests SET status='Completed' WHERE id=%s", (id,))
        else:
            cursor.close()
            conn.close()
            return jsonify({'message':'Not enough stock'}), 400
    
    elif status in ['Accepted','Denied']:
        cursor.execute("UPDATE requests SET status=%s WHERE id=%s", (status, id))
    else:
        cursor.close()
        conn.close()
        return jsonify({'message':'Invalid status'}),400
    
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'message':'Request updated'}),200

# Run server
if __name__=='__main__':
    init_db()
    app.run(debug=True)
