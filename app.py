import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------
# App Setup
# -------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# Render uses DATABASE_URL for PostgreSQL
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///inventory.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------
# Database Models
# -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # HOD or Engineer

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50))  # "received" or "sent"
    item_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    performed_by = db.Column(db.String(80))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class CourierDocket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    docket_number = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------
# Routes
# -------------------
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("login"))

    dockets = CourierDocket.query.all()
    return render_template("main.html", user=user, dockets=dockets)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            return redirect(url_for("home"))
        else:
            flash("Invalid username or password")
    return render_template("main.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        if User.query.filter_by(username=username).first():
            flash("Username already exists")
            return redirect(url_for("register"))

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("User registered successfully")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/add_stock", methods=["POST"])
def add_stock():
    if "user_id" not in session:
        return redirect(url_for("login"))

    item_name = request.form["item_name"]
    quantity = int(request.form["quantity"])

    stock = Stock.query.filter_by(item_name=item_name).first()
    if stock:
        stock.quantity += quantity
        stock.last_updated = datetime.utcnow()
    else:
        stock = Stock(item_name=item_name, quantity=quantity)
        db.session.add(stock)

    user = User.query.get(session["user_id"])
    transaction = Transaction(
        action="received", item_name=item_name, quantity=quantity, performed_by=user.username
    )
    db.session.add(transaction)
    db.session.commit()

    flash("Stock added successfully")
    return redirect(url_for("home"))


@app.route("/send_stock", methods=["POST"])
def send_stock():
    if "user_id" not in session:
        return redirect(url_for("login"))

    item_name = request.form["item_name"]
    quantity = int(request.form["quantity"])

    stock = Stock.query.filter_by(item_name=item_name).first()
    if stock and stock.quantity >= quantity:
        stock.quantity -= quantity
        stock.last_updated = datetime.utcnow()

        user = User.query.get(session["user_id"])
        transaction = Transaction(
            action="sent", item_name=item_name, quantity=quantity, performed_by=user.username
        )
        db.session.add(transaction)
        db.session.commit()
        flash("Stock sent successfully")
    else:
        flash("Not enough stock available")

    return redirect(url_for("home"))


@app.route("/add_docket", methods=["POST"])
def add_docket():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])
    if user.role != "HOD":
        flash("Only HOD can add courier dockets")
        return redirect(url_for("home"))

    docket_number = request.form["docket_number"]
    docket = CourierDocket(docket_number=docket_number)
    db.session.add(docket)
    db.session.commit()
    flash("Docket added successfully")
    return redirect(url_for("home"))


# -------------------
# Initialize Database
# -------------------
with app.app_context():
    db.create_all()


# -------------------
# Run App
# -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
