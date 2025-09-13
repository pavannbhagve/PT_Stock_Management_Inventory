# app.py
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

# Config
app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_in_prod")

# DATABASE_URL environment variable expected (Render provides it)
# Example: postgresql://user:pass@host:port/dbname
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Please set DATABASE_URL environment variable (Postgres URL).")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Models
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)  # login name
    full_name = db.Column(db.String(255), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'hod' or 'engineer'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Stock(db.Model):
    __tablename__ = "stocks"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    is_emergency = db.Column(db.Boolean, default=False)  # true if added as emergency
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EngineerStock(db.Model):
    """Stock held by engineer (after received)"""
    __tablename__ = "engineer_stocks"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    engineer = db.relationship("User", backref="owned_stocks")
    stock = db.relationship("Stock")


class RequestItem(db.Model):
    __tablename__ = "requests"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=True)  # null if emergency_text used
    emergency_text = db.Column(db.String(500), nullable=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(30), default="pending")  # pending / approved / denied / dispatched / received
    docket_number = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    hod_comment = db.Column(db.String(500), nullable=True)

    engineer = db.relationship("User")
    stock = db.relationship("Stock")


class IssueRecord(db.Model):
    """When engineer uses stock for client/site (used stock)."""
    __tablename__ = "issue_records"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    site_name = db.Column(db.String(255), nullable=True)
    issue_notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    engineer = db.relationship("User")
    stock = db.relationship("Stock")


# Helpers
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role:
                if session.get("role") != role:
                    flash("Unauthorized.", "danger")
                    return redirect(url_for("login"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


# Routes
@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "hod":
            return redirect(url_for("hod_dashboard"))
        else:
            return redirect(url_for("engineer_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            session["full_name"] = user.full_name
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials.", "danger")
    return render_template("main.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


# HOD dashboard and actions
@app.route("/hod")
@login_required(role="hod")
def hod_dashboard():
    stocks = Stock.query.order_by(Stock.name).all()
    engineers = User.query.filter_by(role="engineer").order_by(User.username).all()
    requests = RequestItem.query.order_by(RequestItem.created_at.desc()).all()
    issues = IssueRecord.query.order_by(IssueRecord.created_at.desc()).all()
    return render_template(
        "main.html",
        hod=True,
        stocks=stocks,
        engineers=engineers,
        requests=requests,
        issues=issues,
    )


@app.route("/engineer")
@login_required(role="engineer")
def engineer_dashboard():
    stocks = Stock.query.order_by(Stock.name).all()
    my_requests = RequestItem.query.filter_by(engineer_id=session["user_id"]).order_by(RequestItem.created_at.desc()).all()
    my_engineer_stocks = EngineerStock.query.filter_by(engineer_id=session["user_id"]).all()
    issues = IssueRecord.query.filter_by(engineer_id=session["user_id"]).order_by(IssueRecord.created_at.desc()).all()
    return render_template(
        "main.html",
        engineer=True,
        stocks=stocks,
        my_requests=my_requests,
        my_engineer_stocks=my_engineer_stocks,
        issues=issues,
    )


# API endpoints to manage stocks, requests, engineers
@app.route("/api/stock/create", methods=["POST"])
@login_required(role="hod")
def create_stock():
    name = request.form.get("name", "").strip()
    qty = int(request.form.get("quantity", 0))
    is_emergency = bool(request.form.get("is_emergency", False))
    if not name:
        return redirect(url_for("hod_dashboard"))
    # either create new or update existing
    stock = Stock.query.filter(func.lower(Stock.name) == name.lower()).first()
    if stock:
        stock.quantity += qty
        stock.is_emergency = stock.is_emergency or is_emergency
    else:
        stock = Stock(name=name, quantity=qty, is_emergency=is_emergency)
        db.session.add(stock)
    db.session.commit()
    flash(f"Stock '{name}' added/updated.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/stock/update/<int:stock_id>", methods=["POST"])
@login_required(role="hod")
def update_stock(stock_id):
    stock = Stock.query.get_or_404(stock_id)
    name = request.form.get("name", stock.name).strip()
    qty = int(request.form.get("quantity", stock.quantity))
    stock.name = name
    stock.quantity = qty
    db.session.commit()
    flash("Stock updated.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/stock/delete/<int:stock_id>", methods=["POST"])
@login_required(role="hod")
def delete_stock(stock_id):
    stock = Stock.query.get_or_404(stock_id)
    db.session.delete(stock)
    db.session.commit()
    flash("Stock deleted.", "warning")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/engineer/create", methods=["POST"])
@login_required(role="hod")
def create_engineer():
    username = request.form.get("username", "").strip()
    full_name = request.form.get("full_name", "")
    password = request.form.get("password", "").strip()
    if not username or not password:
        flash("Username and password required.", "danger")
        return redirect(url_for("hod_dashboard"))
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        flash("Username already exists.", "danger")
        return redirect(url_for("hod_dashboard"))
    user = User(
        username=username,
        full_name=full_name,
        password_hash=generate_password_hash(password),
        role="engineer",
    )
    db.session.add(user)
    db.session.commit()
    flash("Engineer created.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/engineer/update/<int:user_id>", methods=["POST"])
@login_required(role="hod")
def update_engineer(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != "engineer":
        flash("Invalid user.", "danger")
        return redirect(url_for("hod_dashboard"))
    user.full_name = request.form.get("full_name", user.full_name)
    pwd = request.form.get("password", "").strip()
    if pwd:
        user.password_hash = generate_password_hash(pwd)
    db.session.commit()
    flash("Engineer updated.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/engineer/delete/<int:user_id>", methods=["POST"])
@login_required(role="hod")
def delete_engineer(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != "engineer":
        flash("Invalid user.", "danger")
        return redirect(url_for("hod_dashboard"))
    db.session.delete(user)
    db.session.commit()
    flash("Engineer deleted.", "warning")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/request/create", methods=["POST"])
@login_required(role="engineer")
def create_request():
    stock_id = request.form.get("stock_id")
    emergency_text = request.form.get("emergency_text", "").strip()
    qty = int(request.form.get("quantity", 1))
    if stock_id:
        stock = Stock.query.get(int(stock_id))
        if not stock:
            flash("Invalid stock selected.", "danger")
            return redirect(url_for("engineer_dashboard"))
        # ensure quantity available in HOD for non-emergency items
        if stock.quantity < qty:
            flash("Not enough stock available in HOD. You may create emergency request.", "danger")
            return redirect(url_for("engineer_dashboard"))
        req = RequestItem(
            engineer_id=session["user_id"],
            stock_id=stock.id,
            quantity=qty,
            status="pending",
        )
    else:
        # emergency request with free text
        if not emergency_text:
            flash("Please enter emergency stock name.", "danger")
            return redirect(url_for("engineer_dashboard"))
        req = RequestItem(
            engineer_id=session["user_id"],
            emergency_text=emergency_text,
            quantity=qty,
            status="pending",
        )
    db.session.add(req)
    db.session.commit()
    flash("Request created.", "success")
    return redirect(url_for("engineer_dashboard"))


@app.route("/api/request/act/<int:request_id>", methods=["POST"])
@login_required(role="hod")
def hod_act_request(request_id):
    req = RequestItem.query.get_or_404(request_id)
    action = request.form.get("action")
    comment = request.form.get("comment", "")
    if action == "approve":
        # reduce HOD stock if regular
        if req.stock_id:
            stock = Stock.query.get(req.stock_id)
            if stock.quantity < req.quantity:
                flash("Not enough stock to approve.", "danger")
                return redirect(url_for("hod_dashboard"))
            stock.quantity -= req.quantity
        req.status = "approved"
        req.hod_comment = comment
    elif action == "deny":
        req.status = "denied"
        req.hod_comment = comment
    elif action == "dispatch":
        # set docket number
        docket = request.form.get("docket", "").strip()
        if not docket:
            flash("Docket number required to dispatch.", "danger")
            return redirect(url_for("hod_dashboard"))
        req.docket_number = docket
        req.status = "dispatched"
        req.hod_comment = comment
    elif action == "mark_received":
        # When mark received we add stock to engineer's own inventory
        # If emergency_text exists and stock not present, optionally create stock record with 0
        if req.stock_id:
            stock = Stock.query.get(req.stock_id)
            # add to engineer stock
            eng_stock = EngineerStock.query.filter_by(engineer_id=req.engineer_id, stock_id=stock.id).first()
            if eng_stock:
                eng_stock.quantity += req.quantity
            else:
                eng_stock = EngineerStock(engineer_id=req.engineer_id, stock_id=stock.id, quantity=req.quantity)
                db.session.add(eng_stock)
        else:
            # emergency_text: create a stock entry if not exists and mark as emergency
            name = req.emergency_text.strip()
            stock = Stock.query.filter(func.lower(Stock.name) == name.lower()).first()
            if not stock:
                stock = Stock(name=name, quantity=0, is_emergency=True)
                db.session.add(stock)
                db.session.flush()  # get id
            eng_stock = EngineerStock.query.filter_by(engineer_id=req.engineer_id, stock_id=stock.id).first()
            if eng_stock:
                eng_stock.quantity += req.quantity
            else:
                eng_stock = EngineerStock(engineer_id=req.engineer_id, stock_id=stock.id, quantity=req.quantity)
                db.session.add(eng_stock)
        req.status = "received"
    db.session.commit()
    flash("Request updated.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/request/engineer_cancel/<int:request_id>", methods=["POST"])
@login_required(role="engineer")
def engineer_cancel(request_id):
    req = RequestItem.query.get_or_404(request_id)
    if req.engineer_id != session["user_id"]:
        flash("Unauthorized.", "danger")
        return redirect(url_for("engineer_dashboard"))
    if req.status in ("pending", "denied"):
        db.session.delete(req)
        db.session.commit()
        flash("Request cancelled/deleted.", "warning")
    else:
        flash("Cannot delete request in current state.", "danger")
    return redirect(url_for("engineer_dashboard"))


@app.route("/api/issue/create", methods=["POST"])
@login_required(role="engineer")
def create_issue():
    stock_id = int(request.form.get("stock_id"))
    qty = int(request.form.get("quantity", 1))
    site_name = request.form.get("site_name", "")
    notes = request.form.get("notes", "")
    eng_stock = EngineerStock.query.filter_by(engineer_id=session["user_id"], stock_id=stock_id).first()
    if not eng_stock or eng_stock.quantity < qty:
        flash("Not enough stock in your inventory to issue.", "danger")
        return redirect(url_for("engineer_dashboard"))
    eng_stock.quantity -= qty
    issue = IssueRecord(
        engineer_id=session["user_id"],
        stock_id=stock_id,
        quantity=qty,
        site_name=site_name,
        issue_notes=notes,
    )
    db.session.add(issue)
    db.session.commit()
    flash("Stock issued for site/client.", "success")
    return redirect(url_for("engineer_dashboard"))


# Utility route: simple JSON API to fetch stocks for dropdown/filtering
@app.route("/api/stocks")
@login_required()
def api_stocks():
    stocks = Stock.query.order_by(Stock.name).all()
    data = [{"id": s.id, "name": s.name, "quantity": s.quantity, "is_emergency": s.is_emergency} for s in stocks]
    return jsonify(data)


# Initial setup: create tables and seed HOD user if not exists
with app.app_context():
    db.create_all()
    hod = User.query.filter_by(role="hod").first()
    if not hod:
        # Seed HOD with username PTESPL / ptespl@123
        hod_user = User(
            username="PTESPL",
            full_name="HOD - PTESPL",
            password_hash=generate_password_hash("ptespl@123"),
            role="hod",
        )
        db.session.add(hod_user)
        db.session.commit()
        app.logger.info("Seeded HOD user: PTESPL")


# Run
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
