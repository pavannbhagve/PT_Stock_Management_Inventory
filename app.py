import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------
# App Setup
# -------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecret")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Please set DATABASE_URL environment variable (Postgres URL).")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------
# Models
# -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # "hod" or "engineer"

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class StockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey("stock.id"), nullable=True)
    stock_name = db.Column(db.String(120), nullable=True)  # For emergency stock
    qty = db.Column(db.Integer, nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(20), default="pending")  # pending, in_transit, received
    docket_number = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    requester = db.relationship("User", backref="requests", lazy=True)
    stock = db.relationship("Stock", backref="requests", lazy=True)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="history", lazy=True)

# -------------------
# Helpers
# -------------------
def log_action(user_id, action):
    entry = History(user_id=user_id, action=action)
    db.session.add(entry)
    db.session.commit()

def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None

# -------------------
# Routes
# -------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("Invalid username or password", "danger")
    return render_template("main.html", page="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    if user.role == "hod":
        stocks = Stock.query.all()
        requests = StockRequest.query.order_by(StockRequest.created_at.desc()).all()
        engineers = User.query.filter_by(role="engineer").all()
        logs = History.query.order_by(History.timestamp.desc()).limit(20).all()
        return render_template("main.html", page="hod_dashboard", stocks=stocks, requests=requests, engineers=engineers, logs=logs)

    elif user.role == "engineer":
        stocks = Stock.query.all()
        requests = StockRequest.query.filter_by(requester_id=user.id).order_by(StockRequest.created_at.desc()).all()
        logs = History.query.filter_by(user_id=user.id).order_by(History.timestamp.desc()).limit(20).all()
        return render_template("main.html", page="engineer_dashboard", stocks=stocks, requests=requests, logs=logs)

    return "Unknown role"

# -------------------
# HOD Operations
# -------------------
@app.route("/add_stock", methods=["POST"])
def add_stock():
    user = current_user()
    if not user or user.role != "hod":
        return redirect(url_for("login"))

    name = request.form["name"].strip()
    qty = int(request.form["qty"])
    stock = Stock.query.filter_by(name=name).first()
    if stock:
        stock.quantity += qty
    else:
        stock = Stock(name=name, quantity=qty)
        db.session.add(stock)
    db.session.commit()

    log_action(user.id, f"Added stock {name} (qty {qty})")
    return redirect(url_for("dashboard"))

@app.route("/edit_stock/<int:stock_id>", methods=["POST"])
def edit_stock(stock_id):
    user = current_user()
    if not user or user.role != "hod":
        return redirect(url_for("login"))

    stock = Stock.query.get_or_404(stock_id)
    stock.name = request.form["name"].strip()
    stock.quantity = int(request.form["qty"])
    db.session.commit()

    log_action(user.id, f"Edited stock {stock.name} (qty {stock.quantity})")
    return redirect(url_for("dashboard"))

@app.route("/delete_stock/<int:stock_id>")
def delete_stock(stock_id):
    user = current_user()
    if not user or user.role != "hod":
        return redirect(url_for("login"))

    stock = Stock.query.get_or_404(stock_id)
    db.session.delete(stock)
    db.session.commit()

    log_action(user.id, f"Deleted stock {stock.name}")
    return redirect(url_for("dashboard"))

@app.route("/dispatch/<int:req_id>", methods=["POST"])
def dispatch(req_id):
    user = current_user()
    if not user or user.role != "hod":
        return redirect(url_for("login"))

    req = StockRequest.query.get_or_404(req_id)
    req.status = "in_transit"
    req.docket_number = request.form["docket_number"]
    db.session.commit()

    log_action(user.id, f"Dispatched {req.stock.name if req.stock else req.stock_name} (qty {req.qty}) with docket {req.docket_number}")
    return redirect(url_for("dashboard"))

# -------------------
# Engineer Operations
# -------------------
@app.route("/request_stock", methods=["POST"])
def request_stock():
    user = current_user()
    if not user or user.role != "engineer":
        return redirect(url_for("login"))

    stock_id = request.form.get("stock_id")
    qty = int(request.form["qty"])

    if stock_id and stock_id != "emergency":
        stock = Stock.query.get(int(stock_id))
        req = StockRequest(stock_id=stock.id, qty=qty, requester_id=user.id)
        db.session.add(req)
        db.session.commit()
        log_action(user.id, f"Requested stock {stock.name} (qty {qty})")
    else:
        stock_name = request.form["stock_name"].strip()
        req = StockRequest(stock_name=stock_name, qty=qty, requester_id=user.id)
        db.session.add(req)
        db.session.commit()
        log_action(user.id, f"Emergency request for {stock_name} (qty {qty})")

    return redirect(url_for("dashboard"))

@app.route("/receive/<int:req_id>")
def receive(req_id):
    user = current_user()
    if not user or user.role != "engineer":
        return redirect(url_for("login"))

    req = StockRequest.query.get_or_404(req_id)
    req.status = "received"
    db.session.commit()

    log_action(user.id, f"Received {req.stock.name if req.stock else req.stock_name} (qty {req.qty})")
    return redirect(url_for("dashboard"))

# -------------------
# Init DB (Flask 2.x compatible)
# -------------------
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
