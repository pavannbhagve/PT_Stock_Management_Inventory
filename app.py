import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------
# Flask setup
# -------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"

# SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -------------------
# Models
# -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'HOD' or 'Engineer'

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200))
    location = db.Column(db.String(100))

class RequestStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    stock_id = db.Column(db.Integer, db.ForeignKey('stock.id'))
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Pending')  # Pending / Approved / Rejected
    courier_docket = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class OperationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    action = db.Column(db.String(200))
    stock_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    location = db.Column(db.String(100))
    courier_docket = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------
# Initialize DB and create default HOD
# -------------------
with app.app_context():
    db.create_all()
    hod = User.query.filter_by(username="PTESPL").first()
    if not hod:
        hod = User(username="PTESPL", password=generate_password_hash("ptespl@123"), role="HOD")
        db.session.add(hod)
        db.session.commit()

# -------------------
# Routes
# -------------------
@app.route('/')
def index():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user.role == 'HOD':
            stocks = Stock.query.all()
            requests = RequestStock.query.all()
            logs = OperationLog.query.order_by(OperationLog.timestamp.desc()).all()
            return render_template("main.html", user=user, stocks=stocks, requests=requests, logs=logs)
        else:
            stocks = Stock.query.all()
            requests = RequestStock.query.filter_by(engineer_id=user.id).all()
            return render_template("main.html", user=user, stocks=stocks, requests=requests)
    return redirect(url_for('login'))

# -------------------
# Login
# -------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            flash("Logged in successfully", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials", "danger")
    return render_template("main.html", login_page=True)

# -------------------
# Logout
# -------------------
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("Logged out", "success")
    return redirect(url_for('login'))

# -------------------
# Add Stock (HOD only)
# -------------------
@app.route('/add_stock', methods=['POST'])
def add_stock():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user.role != 'HOD':
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))

    name = request.form['name']
    quantity = int(request.form['quantity'])
    description = request.form['description']
    location = request.form['location']

    stock = Stock(name=name, quantity=quantity, description=description, location=location)
    db.session.add(stock)
    db.session.commit()

    # Log operation
    log = OperationLog(user=user.username, action="Added stock", stock_name=name, quantity=quantity, location=location)
    db.session.add(log)
    db.session.commit()

    flash(f"Stock '{name}' added successfully", "success")
    return redirect(url_for('index'))

# -------------------
# Update Stock (HOD only)
# -------------------
@app.route('/update_stock/<int:stock_id>', methods=['POST'])
def update_stock(stock_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user.role != 'HOD':
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))

    stock = Stock.query.get(stock_id)
    stock.name = request.form['name']
    stock.quantity = int(request.form['quantity'])
    stock.description = request.form['description']
    stock.location = request.form['location']
    db.session.commit()

    # Log operation
    log = OperationLog(user=user.username, action="Updated stock", stock_name=stock.name, quantity=stock.quantity, location=stock.location)
    db.session.add(log)
    db.session.commit()

    flash(f"Stock '{stock.name}' updated successfully", "success")
    return redirect(url_for('index'))

# -------------------
# Delete Stock (HOD only)
# -------------------
@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user.role != 'HOD':
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))

    stock = Stock.query.get(stock_id)
    db.session.delete(stock)
    db.session.commit()

    # Log operation
    log = OperationLog(user=user.username, action="Deleted stock", stock_name=stock.name)
    db.session.add(log)
    db.session.commit()

    flash(f"Stock '{stock.name}' deleted successfully", "success")
    return redirect(url_for('index'))

# -------------------
# Engineer Request Stock
# -------------------
@app.route('/request_stock/<int:stock_id>', methods=['POST'])
def request_stock(stock_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    stock = Stock.query.get(stock_id)
    quantity = int(request.form['quantity'])
    if quantity > stock.quantity:
        flash("Requested quantity exceeds available stock", "danger")
        return redirect(url_for('index'))

    request_stock = RequestStock(engineer_id=user.id, stock_id=stock.id, quantity=quantity)
    db.session.add(request_stock)
    db.session.commit()

    # Log operation
    log = OperationLog(user=user.username, action="Requested stock", stock_name=stock.name, quantity=quantity)
    db.session.add(log)
    db.session.commit()

    flash(f"Request for '{stock.name}' submitted", "success")
    return redirect(url_for('index'))

# -------------------
# HOD Approve/Reject Request & Send Courier
# -------------------
@app.route('/process_request/<int:req_id>', methods=['POST'])
def process_request(req_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if user.role != 'HOD':
        flash("Unauthorized", "danger")
        return redirect(url_for('index'))

    req = RequestStock.query.get(req_id)
    action = request.form['action']
    courier_docket = request.form.get('courier_docket', None)

    if action == 'Approve':
        if req.quantity > req.stock.quantity:
            flash("Not enough stock to approve", "danger")
            return redirect(url_for('index'))
        req.status = 'Approved'
        req.courier_docket = courier_docket
        req.stock.quantity -= req.quantity
        db.session.commit()

        # Log operation
        log = OperationLog(user=user.username, action="Approved stock request", stock_name=req.stock.name, quantity=req.quantity, courier_docket=courier_docket)
        db.session.add(log)
        db.session.commit()
    elif action == 'Reject':
        req.status = 'Rejected'
        db.session.commit()

        # Log operation
        log = OperationLog(user=user.username, action="Rejected stock request", stock_name=req.stock.name, quantity=req.quantity)
        db.session.add(log)
        db.session.commit()

    flash(f"Request {action}", "success")
    return redirect(url_for('index'))

# -------------------
# Run App
# -------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use Render PORT or default 5000
    app.run(host="0.0.0.0", port=port)
    app.run(debug=True)
