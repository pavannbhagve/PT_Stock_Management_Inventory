import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------
# Flask Setup
# ----------------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Database Config
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Please set DATABASE_URL environment variable for PostgreSQL.")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ----------------------------
# Database Models
# ----------------------------

class Engineer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    remarks = db.Column(db.String(200))
    requested_by = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default="Pending")  # Pending, Approved, Denied, In Transit, Received
    docket_number = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class UrgentStockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    remarks = db.Column(db.String(200))
    requested_by = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default="Pending")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class StockUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    engineer = db.Column(db.String(50), nullable=False)
    stock_name = db.Column(db.String(100), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False)
    site_name = db.Column(db.String(100))
    reason = db.Column(db.String(200))
    amc_cmc = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ----------------------------
# Utility
# ----------------------------
def is_hod():
    return "hod" in session and session["hod"] is True

def is_engineer():
    return "engineer" in session

# ----------------------------
# Routes
# ----------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # HOD login fixed
        if username == "PTESPL" and password == "ptespl@123":
            session.clear()
            session["hod"] = True
            return redirect(url_for("dashboard"))

        # Engineer login
        engineer = Engineer.query.filter_by(username=username).first()
        if engineer and check_password_hash(engineer.password, password):
            session.clear()
            session["engineer"] = username
            return redirect(url_for("dashboard"))

        flash("Invalid credentials", "danger")
    return render_template("main.html", page="login")


@app.route("/dashboard")
def dashboard():
    if is_hod():
        engineers = Engineer.query.all()
        stocks = Stock.query.all()
        requests = StockRequest.query.order_by(StockRequest.timestamp.desc()).all()
        urgent_requests = UrgentStockRequest.query.order_by(UrgentStockRequest.timestamp.desc()).all()
        usages = StockUsage.query.order_by(StockUsage.timestamp.desc()).all()
        return render_template("main.html", page="hod", engineers=engineers, stocks=stocks, requests=requests, urgent_requests=urgent_requests, usages=usages)

    elif is_engineer():
        username = session["engineer"]
        stocks = Stock.query.all()
        requests = StockRequest.query.filter_by(requested_by=username).order_by(StockRequest.timestamp.desc()).all()
        urgent_requests = UrgentStockRequest.query.filter_by(requested_by=username).order_by(UrgentStockRequest.timestamp.desc()).all()
        usages = StockUsage.query.filter_by(engineer=username).order_by(StockUsage.timestamp.desc()).all()
        return render_template("main.html", page="engineer", username=username, stocks=stocks, requests=requests, urgent_requests=urgent_requests, usages=usages)

    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----------------------------
# HOD Routes
# ----------------------------
@app.route("/add_engineer", methods=["POST"])
def add_engineer():
    if not is_hod():
        return redirect(url_for("login"))

    username = request.form["username"]
    password = generate_password_hash(request.form["password"])
    eng = Engineer(username=username, password=password)
    db.session.add(eng)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/delete_engineer/<int:id>")
def delete_engineer(id):
    if not is_hod():
        return redirect(url_for("login"))
    Engineer.query.filter_by(id=id).delete()
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/add_stock", methods=["POST"])
def add_stock():
    if not is_hod():
        return redirect(url_for("login"))
    name = request.form["name"]
    qty = int(request.form["quantity"])
    stock = Stock(name=name, quantity=qty)
    db.session.add(stock)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/update_stock/<int:id>", methods=["POST"])
def update_stock(id):
    if not is_hod():
        return redirect(url_for("login"))
    stock = Stock.query.get(id)
    stock.name = request.form["name"]
    stock.quantity = int(request.form["quantity"])
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/delete_stock/<int:id>")
def delete_stock(id):
    if not is_hod():
        return redirect(url_for("login"))
    Stock.query.filter_by(id=id).delete()
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/update_request_status/<int:id>", methods=["POST"])
def update_request_status(id):
    if not is_hod():
        return redirect(url_for("login"))
    req = StockRequest.query.get(id)
    req.status = request.form["status"]
    req.docket_number = request.form.get("docket_number")
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/update_urgent_status/<int:id>", methods=["POST"])
def update_urgent_status(id):
    if not is_hod():
        return redirect(url_for("login"))
    req = UrgentStockRequest.query.get(id)
    req.status = request.form["status"]
    db.session.commit()
    return redirect(url_for("dashboard"))

# ----------------------------
# Engineer Routes
# ----------------------------
@app.route("/request_stock", methods=["POST"])
def request_stock():
    if not is_engineer():
        return redirect(url_for("login"))
    stock_name = request.form["stock_name"]
    qty = int(request.form["quantity"])
    remarks = request.form.get("remarks")
    req = StockRequest(stock_name=stock_name, quantity=qty, remarks=remarks, requested_by=session["engineer"])
    db.session.add(req)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/request_urgent", methods=["POST"])
def request_urgent():
    if not is_engineer():
        return redirect(url_for("login"))
    stock_name = request.form["stock_name"]
    qty = int(request.form["quantity"])
    remarks = request.form.get("remarks")
    req = UrgentStockRequest(stock_name=stock_name, quantity=qty, remarks=remarks, requested_by=session["engineer"])
    db.session.add(req)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/mark_received/<int:id>")
def mark_received(id):
    if not is_engineer():
        return redirect(url_for("login"))
    req = StockRequest.query.get(id)
    if req and req.requested_by == session["engineer"]:
        req.status = "Received"
        db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/use_stock", methods=["POST"])
def use_stock():
    if not is_engineer():
        return redirect(url_for("login"))
    stock_name = request.form["stock_name"]
    qty = int(request.form["quantity"])
    site = request.form["site_name"]
    reason = request.form["reason"]
    amc_cmc = request.form["amc_cmc"]

    usage = StockUsage(engineer=session["engineer"], stock_name=stock_name, quantity_used=qty, site_name=site, reason=reason, amc_cmc=amc_cmc)
    db.session.add(usage)
    db.session.commit()
    return redirect(url_for("dashboard"))

# ----------------------------
# Initialize DB
# ----------------------------
with app.app_context():
    db.create_all()

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
