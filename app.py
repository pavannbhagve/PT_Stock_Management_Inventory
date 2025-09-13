import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Flask setup
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Database
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Please set DATABASE_URL environment variable (Postgres URL).")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # "hod" / "engineer"


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Dispatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey("stock.id"), nullable=False)
    engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    docket_number = db.Column(db.String(200))
    status = db.Column(db.String(50), default="in_transit")  # in_transit / received
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    received_at = db.Column(db.DateTime)

    stock = db.relationship("Stock", backref="dispatches")
    engineer = db.relationship("User", backref="dispatches")


class EmergencyRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default="pending")  # pending / approved / rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    engineer = db.relationship("User", backref="emergency_requests")


# Create tables and default HOD user
with app.app_context():
    db.create_all()
    hod = User.query.filter_by(role="hod").first()
    if not hod:
        default_hod = User(
            username="PTESPL",
            password=generate_password_hash("ptespl@123"),
            role="hod",
        )
        db.session.add(default_hod)
        db.session.commit()
        print("✅ Default HOD created: PTESPL / ptespl@123")


# Routes
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials")
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session["role"]
    if role == "hod":
        stocks = Stock.query.all()
        dispatches = Dispatch.query.order_by(Dispatch.created_at.desc()).all()
        emergencies = EmergencyRequest.query.order_by(EmergencyRequest.created_at.desc()).all()
        return render_template("main.html", role="hod", stocks=stocks, dispatches=dispatches, emergencies=emergencies)

    elif role == "engineer":
        stocks = Stock.query.all()
        dispatches = Dispatch.query.filter_by(engineer_id=session["user_id"]).all()
        emergencies = EmergencyRequest.query.filter_by(engineer_id=session["user_id"]).all()
        return render_template("main.html", role="engineer", stocks=stocks, dispatches=dispatches, emergencies=emergencies)

    return "Unauthorized", 403


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# HOD Actions
@app.route("/add_stock", methods=["POST"])
def add_stock():
    if session.get("role") != "hod":
        return "Unauthorized", 403
    name = request.form["name"]
    qty = int(request.form["quantity"])
    stock = Stock(name=name, quantity=qty)
    db.session.add(stock)
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/edit_stock/<int:stock_id>", methods=["POST"])
def edit_stock(stock_id):
    if session.get("role") != "hod":
        return "Unauthorized", 403
    stock = Stock.query.get(stock_id)
    stock.name = request.form["name"]
    stock.quantity = int(request.form["quantity"])
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/delete_stock/<int:stock_id>")
def delete_stock(stock_id):
    if session.get("role") != "hod":
        return "Unauthorized", 403
    stock = Stock.query.get(stock_id)
    db.session.delete(stock)
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/dispatch/<int:stock_id>", methods=["POST"])
def dispatch(stock_id):
    if session.get("role") != "hod":
        return "Unauthorized", 403
    engineer_id = int(request.form["engineer_id"])
    docket = request.form["docket_number"]

    dispatch = Dispatch(stock_id=stock_id, engineer_id=engineer_id, docket_number=docket, status="in_transit")
    db.session.add(dispatch)
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/update_emergency/<int:req_id>/<string:action>")
def update_emergency(req_id, action):
    if session.get("role") != "hod":
        return "Unauthorized", 403
    req = EmergencyRequest.query.get(req_id)
    if action == "approve":
        req.status = "approved"
    elif action == "reject":
        req.status = "rejected"
    db.session.commit()
    return redirect(url_for("dashboard"))


# Engineer Actions
@app.route("/receive/<int:dispatch_id>")
def receive(dispatch_id):
    if session.get("role") != "engineer":
        return "Unauthorized", 403
    dispatch = Dispatch.query.get(dispatch_id)
    dispatch.status = "received"
    dispatch.received_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/emergency", methods=["POST"])
def emergency():
    if session.get("role") != "engineer":
        return "Unauthorized", 403
    item_name = request.form["item_name"]
    req = EmergencyRequest(engineer_id=session["user_id"], item_name=item_name)
    db.session.add(req)
    db.session.commit()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
