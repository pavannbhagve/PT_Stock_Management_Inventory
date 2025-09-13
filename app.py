import os
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect, url_for, session, flash, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text

# --------------------
# App & DB setup
# --------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# --------------------
# Models
# --------------------
class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # 'hod' or 'engineer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Stock(db.Model):
    __tablename__ = "stock"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Dispatch(db.Model):
    __tablename__ = "dispatch"
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
    __tablename__ = "emergency_request"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    item_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default="pending")  # pending / approved / rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    engineer = db.relationship("User", backref="emergency_requests")


class PersonalStock(db.Model):
    __tablename__ = "personal_stock"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stock_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    engineer = db.relationship("User", backref="personal_stocks")


class StockUsage(db.Model):
    __tablename__ = "stock_usage"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stock_name = db.Column(db.String(200), nullable=False)
    quantity_used = db.Column(db.Integer, nullable=False)
    site_name = db.Column(db.String(200))
    reason = db.Column(db.String(400))
    amc_cmc = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    engineer = db.relationship("User", backref="usage_logs")


# --------------------
# Ensure tables & missing columns
# --------------------
def ensure_columns_and_defaults():
    db.create_all()
    inspector = inspect(db.engine)
    dialect = db.engine.dialect.name

    expected = {
        "user": {"created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "stock": {"created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "dispatch": {
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "received_at": "TIMESTAMP NULL",
        },
        "emergency_request": {"created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "personal_stock": {"created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
        "stock_usage": {"created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"},
    }

    for table, cols in expected.items():
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for col_name, col_sql in cols.items():
            if col_name not in existing:
                try:
                    if dialect == "sqlite":
                        sqlite_sql = col_sql.replace("TIMESTAMP", "DATETIME").replace("NULL", "")
                        sql = f'ALTER TABLE "{table}" ADD COLUMN {col_name} {sqlite_sql};'
                    else:
                        sql = f'ALTER TABLE "{table}" ADD COLUMN {col_name} {col_sql};'
                    db.session.execute(text(sql))
                    db.session.commit()
                except Exception as e:
                    app.logger.warning(f"Could not add column {col_name} to {table}: {e}")


with app.app_context():
    ensure_columns_and_defaults()
    # create default HOD if missing
    if not User.query.filter_by(role="hod").first():
        hod = User(username="PTESPL", password=generate_password_hash("ptespl@123"), role="hod")
        db.session.add(hod)
        db.session.commit()


# --------------------
# Jinja filter for datetime formatting
# --------------------
@app.template_filter("dtfmt")
def format_datetime(value):
    if not value:
        return "-"
    return value.strftime("%d-%m-%Y %I:%M:%S %p")


# --------------------
# Authentication routes
# --------------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["role"] = user.role
            flash(f"Welcome, {user.username}", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))


# --------------------
# Dashboard
# --------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("role")
    user_id = session.get("user_id")
    user = User.query.get(user_id)
    username = user.username if user else ""

    stocks = Stock.query.order_by(Stock.name).all()
    engineers = User.query.filter_by(role="engineer").order_by(User.username).all()

    if role == "hod":
        dispatches = Dispatch.query.order_by(Dispatch.created_at.desc()).all()
        emergencies = EmergencyRequest.query.order_by(EmergencyRequest.created_at.desc()).all()
        personal_stocks = PersonalStock.query.order_by(PersonalStock.created_at.desc()).all()
        usage_logs = StockUsage.query.order_by(StockUsage.created_at.desc()).all()
        return render_template(
            "main.html",
            role=role,
            username=username,
            stocks=stocks,
            engineers=engineers,
            dispatches=dispatches,
            emergencies=emergencies,
            personal_stocks=personal_stocks,
            usage_logs=usage_logs,
        )
    elif role == "engineer":
        dispatches = Dispatch.query.filter_by(engineer_id=user_id).order_by(Dispatch.created_at.desc()).all()
        emergencies = EmergencyRequest.query.filter_by(engineer_id=user_id).order_by(EmergencyRequest.created_at.desc()).all()
        personal_stocks = PersonalStock.query.filter_by(engineer_id=user_id).order_by(PersonalStock.created_at.desc()).all()
        usage_logs = StockUsage.query.filter_by(engineer_id=user_id).order_by(StockUsage.created_at.desc()).all()
        return render_template(
            "main.html",
            role=role,
            username=username,
            stocks=stocks,
            engineers=engineers,
            dispatches=dispatches,
            emergencies=emergencies,
            personal_stocks=personal_stocks,
            usage_logs=usage_logs,
        )
    else:
        return "Unauthorized", 403


# --------------------
# All other routes remain the same (CRUD, dispatch, emergency, personal stock, usage)...
# --------------------

# --------------------
# Run
# --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
