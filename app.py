import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

# Flask setup
app = Flask(__name__)
app.secret_key = "supersecret"

# PostgreSQL connection (Render)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///stock.db"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ------------------
# Models
# ------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # HOD / Engineer


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200))
    location = db.Column(db.String(100))


class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    item_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    status = db.Column(db.String(20), default="Pending")  # Pending/Approved/Rejected
    docket_number = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ------------------
# Routes
# ------------------
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if user.role == "HOD":
        stocks = Stock.query.all()
        requests = Request.query.all()
        logs = Log.query.order_by(Log.timestamp.desc()).all()
        return render_template("main.html", user=user, stocks=stocks, requests=requests, logs=logs)
    else:
        stocks = Stock.query.all()
        requests = Request.query.filter_by(engineer_id=user.id).all()
        return render_template("main.html", user=user, stocks=stocks, requests=requests)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # Hardcoded HOD
        if username == "PTESPL" and password == "ptespl@123":
            session["user_id"] = 0
            session["role"] = "HOD"
            return redirect(url_for("home"))

        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("home"))

        flash("Invalid credentials!")
    return render_template("main.html", login=True)


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]

    if User.query.filter_by(username=username).first():
        flash("Username already exists")
    else:
        new_user = User(username=username, password=password, role="Engineer")
        db.session.add(new_user)
        db.session.commit()
        flash("Engineer registered successfully!")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------
# Stock CRUD (HOD)
# ------------------
@app.route("/add_stock", methods=["POST"])
def add_stock():
    if session.get("role") != "HOD":
        return redirect(url_for("home"))

    item = Stock(
        item_name=request.form["item_name"],
        quantity=int(request.form["quantity"]),
        description=request.form["description"],
        location=request.form["location"],
    )
    db.session.add(item)
    db.session.add(Log(user="HOD", action=f"Added stock {item.item_name} ({item.quantity})"))
    db.session.commit()
    return redirect(url_for("home"))


@app.route("/update_stock/<int:stock_id>", methods=["POST"])
def update_stock(stock_id):
    if session.get("role") != "HOD":
        return redirect(url_for("home"))

    stock = Stock.query.get(stock_id)
    stock.item_name = request.form["item_name"]
    stock.quantity = int(request.form["quantity"])
    stock.description = request.form["description"]
    stock.location = request.form["location"]
    db.session.add(Log(user="HOD", action=f"Updated stock {stock.item_name}"))
    db.session.commit()
    return redirect(url_for("home"))


@app.route("/delete_stock/<int:stock_id>")
def delete_stock(stock_id):
    if session.get("role") != "HOD":
        return redirect(url_for("home"))

    stock = Stock.query.get(stock_id)
    db.session.delete(stock)
    db.session.add(Log(user="HOD", action=f"Deleted stock {stock.item_name}"))
    db.session.commit()
    return redirect(url_for("home"))


# ------------------
# Request Workflow
# ------------------
@app.route("/request_stock", methods=["POST"])
def request_stock():
    if session.get("role") != "Engineer":
        return redirect(url_for("home"))

    user = User.query.get(session["user_id"])
    req = Request(
        engineer_id=user.id,
        item_name=request.form["item_name"],
        quantity=int(request.form["quantity"]),
    )
    db.session.add(req)
    db.session.add(Log(user=user.username, action=f"Requested {req.quantity} of {req.item_name}"))
    db.session.commit()
    return redirect(url_for("home"))


@app.route("/approve_request/<int:req_id>", methods=["POST"])
def approve_request(req_id):
    if session.get("role") != "HOD":
        return redirect(url_for("home"))

    req = Request.query.get(req_id)
    stock = Stock.query.filter_by(item_name=req.item_name).first()

    if stock and stock.quantity >= req.quantity:
        stock.quantity -= req.quantity
        req.status = "Approved"
        req.docket_number = request.form["docket_number"]
        db.session.add(Log(user="HOD", action=f"Approved {req.quantity} {req.item_name}, docket {req.docket_number}"))
    else:
        req.status = "Rejected"
        db.session.add(Log(user="HOD", action=f"Rejected request for {req.item_name}"))

    db.session.commit()
    return redirect(url_for("home"))


@app.route("/reject_request/<int:req_id>")
def reject_request(req_id):
    if session.get("role") != "HOD":
        return redirect(url_for("home"))

    req = Request.query.get(req_id)
    req.status = "Rejected"
    db.session.add(Log(user="HOD", action=f"Rejected request for {req.item_name}"))
    db.session.commit()
    return redirect(url_for("home"))


# ------------------
# DB Init
# ------------------
@app.before_first_request
def create_tables():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
