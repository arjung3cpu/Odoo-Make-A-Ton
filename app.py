import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
db_url = os.getenv("DATABASE_URL", "sqlite:///subscript.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    company = db.Column(db.String(160), default="")
    phone = db.Column(db.String(40), default="")

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    product_type = db.Column(db.String(80), default="Software")
    sales_price = db.Column(db.Numeric(12,2), nullable=False, default=0)
    cost_price = db.Column(db.Numeric(12,2), nullable=False, default=0)
    notes = db.Column(db.Text, default="")

class Variant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    extra_price = db.Column(db.Numeric(12,2), nullable=False, default=0)

class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    name = db.Column(db.String(140), nullable=False)
    price = db.Column(db.Numeric(12,2), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)
    min_quantity = db.Column(db.Integer, default=1)
    available_from = db.Column(db.Date, nullable=True)
    available_until = db.Column(db.Date, nullable=True)
    tax_rate = db.Column(db.Numeric(5,2), default=0)
    allow_pause = db.Column(db.Boolean, default=True)
    allow_early_close = db.Column(db.Boolean, default=True)
    allow_renewal = db.Column(db.Boolean, default=True)

class Discount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)
    value = db.Column(db.Numeric(12,2), nullable=False)
    min_quantity = db.Column(db.Integer, default=1)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    usage_limit = db.Column(db.Integer, nullable=True)
    times_used = db.Column(db.Integer, default=0)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey("variant.id"), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    next_billing_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, default=1)
    payment_terms = db.Column(db.String(80), default="Due on receipt")
    status = db.Column(db.String(20), default="draft")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(60), unique=True, nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscription.id"), nullable=False)
    billing_period_start = db.Column(db.Date, nullable=False)
    billing_period_end = db.Column(db.Date, nullable=False)
    subtotal = db.Column(db.Numeric(12,2), nullable=False)
    tax = db.Column(db.Numeric(12,2), nullable=False, default=0)
    discount = db.Column(db.Numeric(12,2), nullable=False, default=0)
    total = db.Column(db.Numeric(12,2), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="draft")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("subscription_id", "billing_period_start", name="uq_invoice_period"),)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)
    amount = db.Column(db.Numeric(12,2), nullable=False)
    method = db.Column(db.String(40), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.Text, default="")

class QuoteTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=False)
    validity_days = db.Column(db.Integer, default=14)

def money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.")

def parse_date(value):
    return date.fromisoformat(value) if value else None

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

@app.context_processor
def inject_globals():
    return {"me": current_user(), "today": date.today()}

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user().role not in allowed:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco

def next_date(start, frequency):
    if frequency == "daily": return start + timedelta(days=1)
    if frequency == "weekly": return start + timedelta(days=7)
    if frequency == "yearly":
        try: return start.replace(year=start.year + 1)
        except ValueError: return start.replace(month=2, day=28, year=start.year + 1)
    # Monthly: preserve day where possible
    month = start.month + 1
    year = start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    import calendar
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))

def paid_amount(invoice_id):
    return sum((p.amount for p in Payment.query.filter_by(invoice_id=invoice_id).all()), Decimal("0.00"))

def discount_for(sub, subtotal):
    today = date.today()
    product_id = Plan.query.get(sub.plan_id).product_id
    candidates = Discount.query.filter(
        Discount.min_quantity <= sub.quantity,
        or_(Discount.product_id == None, Discount.product_id == product_id),
        or_(Discount.start_date == None, Discount.start_date <= today),
        or_(Discount.end_date == None, Discount.end_date >= today),
        or_(Discount.usage_limit == None, Discount.times_used < Discount.usage_limit)
    ).all()
    if not candidates: return Decimal("0.00"), None
    d = candidates[0]
    amount = subtotal * d.value / Decimal("100") if d.discount_type == "percentage" else d.value
    amount = min(subtotal, amount).quantize(Decimal("0.01"))
    return amount, d

@app.route("/")
def index():
    if current_user(): return redirect(url_for("dashboard"))
    return render_template("login.html", signup=True)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, email, password = request.form["name"].strip(), request.form["email"].strip().lower(), request.form["password"]
        if len(password) <= 8 or not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(not c.isalnum() for c in password):
            flash("Password must be longer than 8 characters and include uppercase, lowercase and a special character.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("That email already has an account.", "danger")
        else:
            customer = Customer(name=name, email=email)
            db.session.add(customer); db.session.flush()
            user = User(name=name, email=email, password_hash=generate_password_hash(password), role="customer", customer_id=customer.id)
            db.session.add(user); db.session.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("login.html", signup=True)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            session.clear(); session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", signup=False)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"].strip().lower()).first()
        if user:
            # Demo flow: reset URL is printed to server console. Configure an email provider for real delivery.
            token = generate_password_hash(f"{user.email}:{app.config['SECRET_KEY']}:{datetime.utcnow().date()}")
            session["reset_user"] = user.id
            session["reset_token"] = token
            print(f"DEMO PASSWORD RESET: user={user.email}. Use the reset link shown in the application after submission.")
            flash("If the account exists, reset instructions have been prepared. For this demo, contact the administrator to reset the password.", "info")
        else:
            flash("If the account exists, reset instructions have been prepared.", "info")
    return render_template("simple_form.html", title="Forgot password", action="Send reset instructions", fields=[("email","Email","email")])


@app.route("/dashboard")
@login_required
def dashboard():
    u = current_user()

    # Customers use their own portal
    if u.role == "customer":
        return redirect(url_for("portal"))

    today = date.today()

    # -------------------------------
    # 1. SUBSCRIPTION STATISTICS
    # -------------------------------

    all_subscriptions = Subscription.query.all()

    active_subscriptions = [
        s for s in all_subscriptions if s.status == "active"
    ]

    active_count = len(active_subscriptions)

    status_counts = {
        "Active": 0,
        "Paused": 0,
        "Draft": 0,
        "Quotation": 0,
        "Confirmed": 0,
        "Closed": 0,
        "Expired": 0
    }

    for s in all_subscriptions:
        label = s.status.capitalize()
        if label in status_counts:
            status_counts[label] += 1

    # -------------------------------
    # 2. MONTHLY RECURRING REVENUE
    # -------------------------------

    mrr = Decimal("0.00")

    for s in active_subscriptions:
        plan = db.session.get(Plan, s.plan_id)

        if not plan:
            continue

        amount = plan.price * s.quantity

        if s.variant_id:
            variant = db.session.get(Variant, s.variant_id)
            if variant:
                amount += variant.extra_price * s.quantity

        if plan.frequency == "daily":
            amount *= Decimal("30.4375")
        elif plan.frequency == "weekly":
            amount *= Decimal("52") / Decimal("12")
        elif plan.frequency == "yearly":
            amount /= Decimal("12")

        mrr += amount

    mrr = mrr.quantize(Decimal("0.01"))

    # -------------------------------
    # 3. PAYMENT AND REVENUE STATISTICS
    # -------------------------------

    all_invoices = Invoice.query.all()
    all_payments = Payment.query.all()

    total_revenue = sum(
        (p.amount for p in all_payments),
        Decimal("0.00")
    )

    total_outstanding = Decimal("0.00")
    paid_count = 0
    unpaid_count = 0
    overdue = []

    for inv in all_invoices:

        if inv.status == "cancelled":
            continue

        received = sum(
            (p.amount for p in all_payments
             if p.invoice_id == inv.id),
            Decimal("0.00")
        )

        balance = max(
            Decimal("0.00"),
            inv.total - received
        )

        total_outstanding += balance

        if balance == 0:
            paid_count += 1
        else:
            unpaid_count += 1

            if inv.due_date and inv.due_date < today:
                overdue.append(inv)

    total_outstanding = total_outstanding.quantize(
        Decimal("0.01")
    )

    overdue_count = len(overdue)

    # -------------------------------
    # 4. MONTHLY REVENUE CHART
    # -------------------------------

    month_labels = []
    monthly_revenue = []

    current_month = today.replace(day=1)

    for offset in range(5, -1, -1):

        month_index = current_month.month - 1 - offset

        year = current_month.year + month_index // 12
        month = month_index % 12 + 1

        month_start = date(year, month, 1)

        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)

        revenue = sum(
            (
                p.amount for p in all_payments
                if p.payment_date
                and month_start <= p.payment_date.date() < next_month
            ),
            Decimal("0.00")
        )

        month_labels.append(month_start.strftime("%b %Y"))
        monthly_revenue.append(float(revenue))

    # -------------------------------
    # 5. RECENT TRANSACTIONS
    # -------------------------------

    recent_payments = (
        Payment.query
        .order_by(Payment.payment_date.desc())
        .limit(7)
        .all()
    )

    recent_transactions = []

    for p in recent_payments:

        inv = db.session.get(Invoice, p.invoice_id)

        if not inv:
            continue

        sub = db.session.get(Subscription, inv.subscription_id)

        customer = (
            db.session.get(Customer, sub.customer_id)
            if sub else None
        )

        recent_transactions.append({
            "invoice": inv.invoice_number,
            "customer": customer.name if customer else "Unknown",
            "amount": float(p.amount),
            "method": p.method,
            "date": p.payment_date.strftime("%d %b %Y")
        })

    # -------------------------------
    # 6. RECENT INVOICES
    # -------------------------------

    recent_invoices = (
        Invoice.query
        .order_by(Invoice.created_at.desc())
        .limit(7)
        .all()
    )

    # -------------------------------
    # 7. RENDER DASHBOARD
    # -------------------------------

    return render_template(
        "dashboard.html",

        active=active_count,
        revenue=total_revenue,
        outstanding=total_outstanding,
        overdue=overdue,

        mrr=mrr,
        paid_count=paid_count,
        unpaid_count=unpaid_count,
        overdue_count=overdue_count,

        total_customers=Customer.query.count(),
        total_subscriptions=len(all_subscriptions),
        total_invoices=len(all_invoices),

        status_labels=list(status_counts.keys()),
        status_values=list(status_counts.values()),

        month_labels=month_labels,
        monthly_revenue=monthly_revenue,

        recent_transactions=recent_transactions,
        invoices=recent_invoices
    )


@app.route("/portal")
@roles("customer")
def portal():
    customer = db.session.get(Customer, current_user().customer_id)

    if not customer:
        abort(404)

    # Get only this customer's subscriptions
    subscriptions = Subscription.query.filter_by(
        customer_id=customer.id
    ).order_by(Subscription.id.desc()).all()

    # Get only invoices belonging to these subscriptions
    subscription_ids = [s.id for s in subscriptions]

    invoices = []

    if subscription_ids:
        invoices = Invoice.query.filter(
            Invoice.subscription_id.in_(subscription_ids)
        ).order_by(Invoice.id.desc()).all()

    # Load plan names
    plans = Plan.query.all()
    plan_map = {p.id: p for p in plans}

    # Load payments for these invoices
    invoice_ids = [i.id for i in invoices]

    payments = []

    if invoice_ids:
        payments = Payment.query.filter(
            Payment.invoice_id.in_(invoice_ids)
        ).order_by(Payment.id.desc()).all()

    # Calculate payment totals for each invoice
    paid_by_invoice = {}

    for payment in payments:
        paid_by_invoice[payment.invoice_id] = (
            paid_by_invoice.get(payment.invoice_id, 0)
            + payment.amount
        )

    total_paid = sum(
        (payment.amount for payment in payments), 0
    )

    outstanding = sum(
        (
            max(invoice.total - paid_by_invoice.get(invoice.id, 0), 0)
            for invoice in invoices
            if invoice.status != "cancelled"
        ),
        0
    )

    active_subscriptions = sum(
        1 for s in subscriptions if s.status == "active"
    )

    return render_template(
        "portal.html",
        customer=customer,
        subscriptions=subscriptions,
        invoices=invoices,
        payments=payments,
        plan_map=plan_map,
        paid_by_invoice=paid_by_invoice,
        total_paid=total_paid,
        outstanding=outstanding,
        active_subscriptions=active_subscriptions,
        total_subscriptions=len(subscriptions)
    )

@app.route("/customers", methods=["GET", "POST"])
@roles("admin", "staff")
def customers():
    if request.method == "POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower()
        if Customer.query.filter_by(email=email).first():
            flash("Customer email already exists.", "danger")
        else:
            c=Customer(name=name,email=email,company=request.form.get("company",""),phone=request.form.get("phone",""))
            db.session.add(c); db.session.commit(); flash("Customer created.", "success")
        return redirect(url_for("customers"))
    return render_template("customers.html", customers=Customer.query.order_by(Customer.id.desc()).all())

@app.route("/staff", methods=["GET", "POST"])
@roles("admin")
def staff():
    if request.method == "POST":
        email=request.form["email"].strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
        else:
            password=request.form["password"]
            if len(password)<=8 or not any(x.isupper() for x in password) or not any(x.islower() for x in password) or not any(not x.isalnum() for x in password):
                flash("Password must be >8 chars and contain upper, lower and special characters.", "danger")
            else:
                db.session.add(User(name=request.form["name"],email=email,password_hash=generate_password_hash(password),role="staff"))
                db.session.commit(); flash("Staff account created.", "success")
        return redirect(url_for("staff"))
    return render_template("staff.html", users=User.query.filter_by(role="staff").all())

@app.route("/products", methods=["GET", "POST"])
@roles("admin", "staff")
def products():
    if request.method == "POST":
        p=Product(name=request.form["name"],product_type=request.form.get("product_type","Software"),sales_price=money(request.form["sales_price"]),cost_price=money(request.form.get("cost_price",0)),notes=request.form.get("notes",""))
        db.session.add(p); db.session.flush()
        vname=request.form.get("variant_name","").strip()
        if vname: db.session.add(Variant(product_id=p.id,name=vname,extra_price=money(request.form.get("variant_price",0))))
        db.session.commit(); flash("Product created.", "success")
        return redirect(url_for("products"))
    return render_template("products.html", products=Product.query.order_by(Product.id.desc()).all())

@app.route("/plans", methods=["GET", "POST"])
@roles("admin", "staff")
def plans():
    if request.method == "POST":
        p=Plan(product_id=int(request.form["product_id"]),name=request.form["name"],price=money(request.form["price"]),frequency=request.form["frequency"],min_quantity=int(request.form.get("min_quantity",1)),available_from=parse_date(request.form.get("available_from")),available_until=parse_date(request.form.get("available_until")),tax_rate=money(request.form.get("tax_rate",0)),allow_pause=bool(request.form.get("allow_pause")),allow_early_close=bool(request.form.get("allow_early_close")),allow_renewal=bool(request.form.get("allow_renewal")))
        db.session.add(p); db.session.commit(); flash("Plan created.", "success")
        return redirect(url_for("plans"))
    return render_template("plans.html", plans=Plan.query.all(), products=Product.query.all())


@app.route("/subscriptions", methods=["GET", "POST"])
@roles("admin", "staff")
def subscriptions():
    if request.method == "POST":
        try:
            customer_id = int(request.form["customer_id"])
            plan_id = int(request.form["plan_id"])
            qty = int(request.form.get("quantity", 1))
            variant_id = (
                int(request.form["variant_id"])
                if request.form.get("variant_id")
                else None
            )
        except (ValueError, TypeError, KeyError):
            flash("Please enter valid subscription details.", "danger")
            return redirect(url_for("subscriptions"))

        customer = db.session.get(Customer, customer_id)
        plan = db.session.get(Plan, plan_id)
        start = parse_date(request.form.get("start_date")) or date.today()
        expiry = parse_date(request.form.get("expiry_date"))
        status = request.form.get("status", "active")

        allowed_statuses = [
            "draft", "quotation", "confirmed", "active",
            "paused", "closed", "expired"
        ]

        if not customer or not plan:
            flash("Please select a valid customer and plan.", "danger")
        elif qty < plan.min_quantity:
            flash(
                f"Minimum quantity for this plan is {plan.min_quantity}.",
                "danger"
            )
        elif status not in allowed_statuses:
            flash("Invalid subscription status.", "danger")
        elif expiry and expiry < start:
            flash("Expiry date cannot be before the start date.", "danger")
        elif (
            (plan.available_from and start < plan.available_from)
            or (plan.available_until and start > plan.available_until)
        ):
            flash("This plan is not available on the selected date.", "danger")
        else:
            subscription = Subscription(
                customer_id=customer.id,
                plan_id=plan.id,
                variant_id=variant_id,
                start_date=start,
                expiry_date=expiry,
                next_billing_date=start,
                quantity=qty,
                payment_terms=request.form.get(
                    "payment_terms", "Due on receipt"
                ),
                status=status
            )

            db.session.add(subscription)
            db.session.commit()
            flash("Subscription created successfully.", "success")

        return redirect(url_for("subscriptions"))

    # Load subscriptions and related names
    all_subscriptions = Subscription.query.order_by(
        Subscription.id.desc()
    ).all()

    customers = Customer.query.order_by(Customer.name).all()
    plans = Plan.query.order_by(Plan.name).all()
    variants = Variant.query.all()

    customer_map = {c.id: c for c in customers}
    plan_map = {p.id: p for p in plans}
    variant_map = {v.id: v for v in variants}

    # Search and status filtering
    search = request.args.get("search", "").strip().lower()
    selected_status = request.args.get("status", "").strip().lower()

    filtered_subscriptions = []

    for s in all_subscriptions:
        customer = customer_map.get(s.customer_id)
        plan = plan_map.get(s.plan_id)

        customer_name = customer.name if customer else ""
        plan_name = plan.name if plan else ""

        matches_search = (
            not search
            or search in customer_name.lower()
            or search in plan_name.lower()
            or search in str(s.id)
        )

        matches_status = (
            not selected_status or s.status.lower() == selected_status
        )

        if matches_search and matches_status:
            filtered_subscriptions.append(s)

    return render_template(
        "subscriptions.html",
        subscriptions=filtered_subscriptions,
        customers=customers,
        plans=plans,
        variants=variants,
        customer_map=customer_map,
        plan_map=plan_map,
        variant_map=variant_map,
        today=date.today().isoformat(),
        search=search,
        selected_status=selected_status
    )


@app.route("/subscriptions/<int:sid>/status", methods=["POST"])
@roles("admin", "staff")
def subscription_status(sid):
    subscription = db.session.get(Subscription, sid) or abort(404)

    new_status = request.form.get("status", "").lower()

    allowed_statuses = [
        "draft", "quotation", "confirmed", "active",
        "paused", "closed", "expired"
    ]

    if new_status not in allowed_statuses:
        abort(400)

    plan = db.session.get(Plan, subscription.plan_id)

    if new_status == "paused" and not plan.allow_pause:
        flash("This plan cannot be paused.", "danger")

    elif (
        new_status == "closed"
        and not plan.allow_early_close
        and (
            not subscription.expiry_date
            or subscription.expiry_date > date.today()
        )
    ):
        flash("Early closure is disabled for this plan.", "danger")

    else:
        subscription.status = new_status
        db.session.commit()
        flash("Subscription status updated successfully.", "success")

    return redirect(url_for("subscriptions"))


@app.route("/invoices", methods=["GET"])
@roles("admin", "staff")
def invoices():
    return render_template("invoices.html", invoices=Invoice.query.order_by(Invoice.id.desc()).all())

@app.route("/invoices/generate", methods=["POST"])
@roles("admin", "staff")
def generate_invoices():
    created=0
    today=date.today()
    for s in Subscription.query.filter_by(status="active").all():
        if s.next_billing_date > today: continue
        plan=db.session.get(Plan,s.plan_id)
        if s.expiry_date and s.next_billing_date > s.expiry_date:
            s.status="expired"; continue
        start=s.next_billing_date
        end=next_date(start,plan.frequency)
        exists=Invoice.query.filter_by(subscription_id=s.id,billing_period_start=start).first()
        if exists: continue
        base=plan.price * s.quantity
        if s.variant_id:
            variant=db.session.get(Variant,s.variant_id)
            if variant: base += variant.extra_price * s.quantity
        discount, applied=discount_for(s,base)
        taxable=max(Decimal("0"),base-discount)
        tax=(taxable * plan.tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        total=(taxable+tax).quantize(Decimal("0.01"))
        inv=Invoice(invoice_number=f"SUB-{datetime.utcnow().strftime('%Y%m%d')}-{s.id}-{start.strftime('%Y%m%d')}",subscription_id=s.id,billing_period_start=start,billing_period_end=end-timedelta(days=1),subtotal=base,tax=tax,discount=discount,total=total,due_date=start+timedelta(days=7),status="confirmed")
        db.session.add(inv)
        if applied: applied.times_used += 1
        s.next_billing_date=end
        created+=1
    db.session.commit()
    flash(f"Generated {created} invoice(s). Existing billing periods were skipped.", "success")
    return redirect(url_for("invoices"))

@app.route("/invoices/<int:iid>/status", methods=["POST"])
@roles("admin", "staff")
def invoice_status(iid):
    inv=db.session.get(Invoice,iid) or abort(404)
    new=request.form["status"]
    if new not in ["confirmed","cancelled"]: abort(400)
    inv.status=new; db.session.commit(); flash("Invoice updated.", "success")
    return redirect(url_for("invoices"))

@app.route("/payments", methods=["GET", "POST"])
@roles("admin", "staff")
def payments():
    if request.method=="POST":
        inv=db.session.get(Invoice,int(request.form["invoice_id"]))
        amount=money(request.form["amount"])
        if not inv or inv.status=="cancelled" or amount<=0:
            flash("Select a valid invoice and positive payment.", "danger")
        elif paid_amount(inv.id)+amount > inv.total:
            flash("Payment exceeds the remaining invoice balance.", "danger")
        else:
            db.session.add(Payment(invoice_id=inv.id,amount=amount,method=request.form["method"],note=request.form.get("note","")))
            db.session.flush()
            if paid_amount(inv.id) == inv.total: inv.status="paid"
            db.session.commit(); flash("Payment recorded.", "success")
        return redirect(url_for("payments"))
    return render_template("payments.html", payments=Payment.query.order_by(Payment.id.desc()).all(), invoices=Invoice.query.filter(Invoice.status!="cancelled").all(), paid_amount=paid_amount)

@app.route("/discounts", methods=["GET", "POST"])
@roles("admin")
def discounts():
    if request.method=="POST":
        d=Discount(name=request.form["name"],discount_type=request.form["discount_type"],value=money(request.form["value"]),min_quantity=int(request.form.get("min_quantity",1)),start_date=parse_date(request.form.get("start_date")),end_date=parse_date(request.form.get("end_date")),usage_limit=int(request.form["usage_limit"]) if request.form.get("usage_limit") else None,product_id=int(request.form["product_id"]) if request.form.get("product_id") else None)
        db.session.add(d); db.session.commit(); flash("Discount rule created.", "success")
        return redirect(url_for("discounts"))
    return render_template("discounts.html", discounts=Discount.query.all(), products=Product.query.all())

@app.route("/quotes", methods=["GET", "POST"])
@roles("admin", "staff")
def quotes():
    if request.method=="POST":
        db.session.add(QuoteTemplate(name=request.form["name"],plan_id=int(request.form["plan_id"]),validity_days=int(request.form.get("validity_days",14))))
        db.session.commit(); flash("Quotation template saved.", "success")
        return redirect(url_for("quotes"))
    return render_template("quotes.html", quotes=QuoteTemplate.query.all(), plans=Plan.query.all())

@app.route("/reset-demo-admin")
def reset_demo_admin():
    # Local demo convenience only. Disable/remove before any public deployment.
    if not app.debug: abort(404)
    u=User.query.filter_by(email="admin@subscript.local").first()
    if u: u.password_hash=generate_password_hash("Admin@12345"); db.session.commit()
    return "Demo admin password reset."

@app.errorhandler(403)
def forbidden(e): return render_template("message.html", title="Access denied", message="You do not have permission to access this page."),403

@app.errorhandler(404)
def not_found(e): return render_template("message.html", title="Not found", message="The requested page was not found."),404

def seed_demo():
    if User.query.count()==0:
        db.session.add(User(name="Demo Admin",email="admin@subscript.local",password_hash=generate_password_hash("Admin@12345"),role="admin"))
        db.session.commit()
    if os.getenv("SEED_DEMO","1")=="1" and Product.query.count()==0:
        c=Customer(name="Rahul Sharma",email="rahul@example.com",company="Rahul Traders",phone="9876543210")
        p=Product(name="Business Software",product_type="Software",sales_price=1000,cost_price=400,notes="Demo product")
        db.session.add_all([c,p]); db.session.flush()
        plan=Plan(product_id=p.id,name="Business Monthly",price=1000,frequency="monthly",min_quantity=1,tax_rate=18)
        db.session.add(plan); db.session.commit()
        s=Subscription(customer_id=c.id,plan_id=plan.id,start_date=date.today(),next_billing_date=date.today(),expiry_date=None,quantity=1,status="active")
        db.session.add(s); db.session.commit()

with app.app_context():
    db.create_all()
    seed_demo()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
