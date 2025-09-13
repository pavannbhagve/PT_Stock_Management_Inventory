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
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Stock(db.Model):
    __tablename__ = "stocks"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    is_emergency = db.Column(db.Boolean, default=False)  # if item marked emergency
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EngineerStock(db.Model):
    __tablename__ = "engineer_stocks"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    engineer = db.relationship("User", backref="owned_stocks")
    stock = db.relationship("Stock")


class RequestItem(db.Model):
    __tablename__ = "requests"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=True)  # null for emergency text
    emergency_text = db.Column(db.String(500), nullable=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(30), default="pending")  # pending / approved / in_transit / received / denied
    docket_number = db.Column(db.String(255), nullable=True)
    hod_comment = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    engineer = db.relationship("User")
    stock = db.relationship("Stock")


class IssueRecord(db.Model):
    __tablename__ = "issue_records"
    id = db.Column(db.Integer, primary_key=True)
    engineer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    site_name = db.Column(db.String(255), nullable=True)
    reason = db.Column(db.String(500), nullable=True)
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
            if role and session.get("role") != role:
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
        flash("Invalid credentials.", "danger")
    return render_template("main.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


# HOD dashboard
@app.route("/hod")
@login_required(role="hod")
def hod_dashboard():
    stocks = Stock.query.order_by(Stock.name).all()
    engineers = User.query.filter_by(role="engineer").order_by(User.username).all()
    requests = RequestItem.query.order_by(RequestItem.created_at.desc()).all()
    engineer_stocks = EngineerStock.query.order_by(EngineerStock.created_at.desc()).all()
    issues = IssueRecord.query.order_by(IssueRecord.created_at.desc()).all()
    return render_template(
        "main.html",
        hod=True,
        stocks=stocks,
        engineers=engineers,
        requests=requests,
        engineer_stocks=engineer_stocks,
        issues=issues,
    )


# Engineer dashboard
@app.route("/engineer")
@login_required(role="engineer")
def engineer_dashboard():
    stocks = Stock.query.order_by(Stock.name).all()
    my_requests = RequestItem.query.filter_by(engineer_id=session["user_id"]).order_by(RequestItem.created_at.desc()).all()
    my_engineer_stocks = EngineerStock.query.filter_by(engineer_id=session["user_id"]).all()
    my_issues = IssueRecord.query.filter_by(engineer_id=session["user_id"]).order_by(IssueRecord.created_at.desc()).all()
    return render_template(
        "main.html",
        engineer=True,
        stocks=stocks,
        my_requests=my_requests,
        my_engineer_stocks=my_engineer_stocks,
        my_issues=my_issues,
    )


# HOD: Stock CRUD
@app.route("/api/stock/add", methods=["POST"])
@login_required(role="hod")
def api_add_stock():
    name = request.form.get("name", "").strip()
    qty = int(request.form.get("quantity", 0))
    if not name:
        flash("Stock name required.", "danger")
        return redirect(url_for("hod_dashboard"))
    stock = Stock.query.filter(func.lower(Stock.name) == name.lower()).first()
    if stock:
        stock.quantity = qty
    else:
        stock = Stock(name=name, quantity=qty)
        db.session.add(stock)
    db.session.commit()
    flash("Stock added/updated.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/stock/edit/<int:stock_id>", methods=["POST"])
@login_required(role="hod")
def api_edit_stock(stock_id):
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
def api_delete_stock(stock_id):
    stock = Stock.query.get_or_404(stock_id)
    db.session.delete(stock)
    db.session.commit()
    flash("Stock deleted.", "warning")
    return redirect(url_for("hod_dashboard"))


# HOD: Engineer management
@app.route("/api/engineer/add", methods=["POST"])
@login_required(role="hod")
def api_add_engineer():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    if not username or not password:
        flash("Username & password required.", "danger")
        return redirect(url_for("hod_dashboard"))
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        flash("Username already exists.", "danger")
        return redirect(url_for("hod_dashboard"))
    user = User(
        username=username,
        full_name=request.form.get("full_name", ""),
        password_hash=generate_password_hash(password),
        role="engineer",
    )
    db.session.add(user)
    db.session.commit()
    flash("Engineer created.", "success")
    return redirect(url_for("hod_dashboard"))


@app.route("/api/engineer/delete/<int:user_id>", methods=["POST"])
@login_required(role="hod")
def api_delete_engineer(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != "engineer":
        flash("Invalid user.", "danger")
        return redirect(url_for("hod_dashboard"))
    db.session.delete(user)
    db.session.commit()
    flash("Engineer deleted.", "warning")
    return redirect(url_for("hod_dashboard"))


# Engineer: Create request (normal or urgent)
@app.route("/api/request/create", methods=["POST"])
@login_required(role="engineer")
def api_create_request():
    stock_id = request.form.get("stock_id") or None
    emergency_text = request.form.get("emergency_text", "").strip() or None
    qty = int(request.form.get("quantity", 1))
    # If normal stock chosen, ensure HOD has enough quantity
    if stock_id:
        stock = Stock.query.get(int(stock_id))
        if not stock:
            flash("Invalid stock selected.", "danger")
            return redirect(url_for("engineer_dashboard"))
        if stock.quantity < qty:
            flash("Not enough stock in HOD. Consider urgent request.", "danger")
            return redirect(url_for("engineer_dashboard"))
        req = RequestItem(engineer_id=session["user_id"], stock_id=stock.id, quantity=qty, status="pending")
    else:
        if not emergency_text:
            flash("Provide emergency stock name or select normal stock.", "danger")
            return redirect(url_for("engineer_dashboard"))
        req = RequestItem(engineer_id=session["user_id"], emergency_text=emergency_text, quantity=qty, status="pending")
    db.session.add(req)
    db.session.commit()
    flash("Request created.", "success")
    return redirect(url_for("engineer_dashboard"))


# HOD: Act on request (approve / deny / dispatch)
@app.route("/api/request/act/<int:request_id>", methods=["POST"])
@login_required(role="hod")
def api_request_act(request_id):
    req = RequestItem.query.get_or_404(request_id)
    action = request.form.get("action")
    comment = request.form.get("comment", "")
    if action == "approve":
        # reduce HOD stock if it's a normal stock
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
        docket = request.form.get("docket", "").strip()
        if not docket:
            flash("Docket number required to dispatch.", "danger")
            return redirect(url_for("hod_dashboard"))
        # set docket and mark in_transit
        req.docket_number = docket
        req.status = "in_transit"
        req.hod_comment = comment

    req.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Request updated.", "success")
    return redirect(url_for("hod_dashboard"))


# Engineer: Mark Received (when in_transit)
@app.route("/api/request/mark_received/<int:request_id>", methods=["POST"])
@login_required(role="engineer")
def api_mark_received(request_id):
    req = RequestItem.query.get_or_404(request_id)
    if req.engineer_id != session["user_id"]:
        flash("Unauthorized.", "danger")
        return redirect(url_for("engineer_dashboard"))
    if req.status != "in_transit":
        flash("Only in-transit requests can be marked received.", "danger")
        return redirect(url_for("engineer_dashboard"))

    # Add to engineer stock (create stock record if emergency)
    if req.stock_id:
        stock = Stock.query.get(req.stock_id)
    else:
        # emergency: create Stock if missing (HOD may later edit)
        name = (req.emergency_text or "").strip()
        stock = Stock.query.filter(func.lower(Stock.name) == name.lower()).first()
        if not stock:
            stock = Stock(name=name, quantity=0, is_emergency=True)
            db.session.add(stock)
            db.session.flush()

    eng_stock = EngineerStock.query.filter_by(engineer_id=req.engineer_id, stock_id=stock.id).first()
    if eng_stock:
        eng_stock.quantity += req.quantity
    else:
        eng_stock = EngineerStock(engineer_id=req.engineer_id, stock_id=stock.id, quantity=req.quantity)
        db.session.add(eng_stock)

    req.status = "received"
    req.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Marked as received. Added to your personal stock.", "success")
    return redirect(url_for("engineer_dashboard"))


# Engineer: Cancel a pending request
@app.route("/api/request/cancel/<int:request_id>", methods=["POST"])
@login_required(role="engineer")
def api_cancel_request(request_id):
    req = RequestItem.query.get_or_404(request_id)
    if req.engineer_id != session["user_id"]:
        flash("Unauthorized.", "danger")
        return redirect(url_for("engineer_dashboard"))
    if req.status in ("pending", "denied"):
        db.session.delete(req)
        db.session.commit()
        flash("Request deleted.", "warning")
    else:
        flash("Cannot delete request in current state.", "danger")
    return redirect(url_for("engineer_dashboard"))


# Engineer: Add / Update personal stock (manual)
@app.route("/api/engineer/stock_add", methods=["POST"])
@login_required(role="engineer")
def api_engineer_stock_add():
    stock_name = request.form.get("stock_name", "").strip()
    qty = int(request.form.get("quantity", 0))
    if not stock_name or qty <= 0:
        flash("Stock name and positive qty required.", "danger")
        return redirect(url_for("engineer_dashboard"))
    stock = Stock.query.filter(func.lower(Stock.name) == stock_name.lower()).first()
    if not stock:
        # allow engineer to record personal stock even if HOD hasn't created
        stock = Stock(name=stock_name, quantity=0, is_emergency=True)
        db.session.add(stock)
        db.session.flush()
    eng_stock = EngineerStock.query.filter_by(engineer_id=session["user_id"], stock_id=stock.id).first()
    if eng_stock:
        eng_stock.quantity = qty
    else:
        eng_stock = EngineerStock(engineer_id=session["user_id"], stock_id=stock.id, quantity=qty)
        db.session.add(eng_stock)
    db.session.commit()
    flash("Personal stock added/updated.", "success")
    return redirect(url_for("engineer_dashboard"))


# Engineer: Issue stock to site (stock usage)
@app.route("/api/issue/add", methods=["POST"])
@login_required(role="engineer")
def api_issue_add():
    stock_id = int(request.form.get("stock_id", 0))
    qty = int(request.form.get("quantity", 0))
    site = request.form.get("site_name", "").strip()
    reason = request.form.get("reason", "").strip()
    if qty <= 0:
        flash("Quantity should be > 0.", "danger")
        return redirect(url_for("engineer_dashboard"))
    eng_stock = EngineerStock.query.filter_by(engineer_id=session["user_id"], stock_id=stock_id).first()
    if not eng_stock or eng_stock.quantity < qty:
        flash("Not enough personal stock.", "danger")
        return redirect(url_for("engineer_dashboard"))
    eng_stock.quantity -= qty
    issue = IssueRecord(engineer_id=session["user_id"], stock_id=stock_id, quantity=qty, site_name=site, reason=reason)
    db.session.add(issue)
    db.session.commit()
    flash("Stock issued (logged).", "success")
    return redirect(url_for("engineer_dashboard"))


# Utility: JSON stocks (for client-side dropdown)
@app.route("/api/stocks")
@login_required()
def api_stocks():
    stocks = Stock.query.order_by(Stock.name).all()
    return jsonify([{"id": s.id, "name": s.name, "quantity": s.quantity} for s in stocks])


# Startup: create tables and seed default HOD if missing
with app.app_context():
    db.create_all()
    hod = User.query.filter_by(role="hod").first()
    if not hod:
        hod_user = User(
            username="PTESPL",
            full_name="HOD - PTESPL",
            password_hash=generate_password_hash("ptespl@123"),
            role="hod",
        )
        db.session.add(hod_user)
        db.session.commit()
        app.logger.info("Seeded HOD user: PTESPL")


# Run (for local dev; gunicorn will import app)
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
