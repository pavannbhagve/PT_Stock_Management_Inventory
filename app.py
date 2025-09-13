import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)

# PostgreSQL DATABASE_URL from Render or local fallback
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/inventory_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------------------------
# Models
# -------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'HOD' or 'Engineer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Dispatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'), nullable=False)
    engineer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    docket_number = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='In Transit')  # 'In Transit' or 'Received'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    received_at = db.Column(db.DateTime, nullable=True)

class EmergencyRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_name = db.Column(db.String(100), nullable=False)
    engineer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # 'Pending', 'Accepted', 'Denied'
    hod_comments = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# -------------------------
# Ensure default HOD exists
# -------------------------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(role='HOD').first():
        hod = User(username='PTESPL', password=generate_password_hash('ptespl@123'), role='HOD')
        db.session.add(hod)
        db.session.commit()

# -------------------------
# Login / Logout
# -------------------------
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('main.html', login_page=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# -------------------------
# Dashboard
# -------------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    hods = User.query.filter_by(role='HOD').all()
    engineers = User.query.filter_by(role='Engineer').all()
    stocks = Stock.query.all()
    dispatches = Dispatch.query.all()
    emergencies = EmergencyRequest.query.all()

    return render_template('main.html',
                           login_page=False,
                           user=user,
                           hods=hods,
                           engineers=engineers,
                           stocks=stocks,
                           dispatches=dispatches,
                           emergencies=emergencies)

# -------------------------
# CRUD Stock (HOD only)
# -------------------------
@app.route('/add_stock', methods=['POST'])
def add_stock():
    if session.get('role') != 'HOD':
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    name = request.form['stock_name']
    qty = int(request.form['quantity'])
    stock = Stock(name=name, quantity=qty)
    db.session.add(stock)
    db.session.commit()
    flash("Stock added", 'success')
    return redirect(url_for('dashboard'))

@app.route('/update_stock/<int:id>', methods=['POST'])
def update_stock(id):
    if session.get('role') != 'HOD':
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    stock = Stock.query.get(id)
    stock.name = request.form['stock_name']
    stock.quantity = int(request.form['quantity'])
    db.session.commit()
    flash("Stock updated", 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_stock/<int:id>')
def delete_stock(id):
    if session.get('role') != 'HOD':
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    stock = Stock.query.get(id)
    db.session.delete(stock)
    db.session.commit()
    flash("Stock deleted", 'success')
    return redirect(url_for('dashboard'))

# -------------------------
# Dispatch workflow
# -------------------------
@app.route('/dispatch_stock', methods=['POST'])
def dispatch_stock():
    if session.get('role') != 'HOD':
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    stock_id = int(request.form['stock_id'])
    engineer_id = int(request.form['engineer_id'])
    docket = request.form.get('docket_number')
    stock = Stock.query.get(stock_id)
    if stock.quantity < 1:
        flash("Not enough stock", 'danger')
        return redirect(url_for('dashboard'))
    stock.quantity -= 1
    dispatch = Dispatch(stock_id=stock_id, engineer_id=engineer_id, docket_number=docket)
    db.session.add(dispatch)
    db.session.commit()
    flash("Stock dispatched", 'success')
    return redirect(url_for('dashboard'))

@app.route('/receive_dispatch/<int:id>')
def receive_dispatch(id):
    dispatch = Dispatch.query.get(id)
    if session.get('role') != 'Engineer' or dispatch.engineer_id != session['user_id']:
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    dispatch.status = 'Received'
    dispatch.received_at = datetime.utcnow()
    db.session.commit()
    flash("Stock marked as received", 'success')
    return redirect(url_for('dashboard'))

# -------------------------
# Emergency Requests
# -------------------------
@app.route('/request_emergency', methods=['POST'])
def request_emergency():
    if session.get('role') != 'Engineer':
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    stock_name = request.form['stock_name']
    emergency = EmergencyRequest(stock_name=stock_name, engineer_id=session['user_id'])
    db.session.add(emergency)
    db.session.commit()
    flash("Emergency request submitted", 'success')
    return redirect(url_for('dashboard'))

@app.route('/process_emergency/<int:id>/<action>', methods=['POST'])
def process_emergency(id, action):
    if session.get('role') != 'HOD':
        flash("Unauthorized", 'danger')
        return redirect(url_for('dashboard'))
    emergency = EmergencyRequest.query.get(id)
    if action == 'accept':
        emergency.status = 'Accepted'
    elif action == 'deny':
        emergency.status = 'Denied'
    emergency.hod_comments = request.form.get('hod_comments')
    db.session.commit()
    flash(f"Emergency request {emergency.status}", 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
