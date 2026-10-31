# Subscript – Subscription Management System

A hackathon MVP for managing customers, products, plans, subscriptions, recurring invoices, discounts, payments and dashboard reporting.

## Stack
- Python Flask
- Flask-SQLAlchemy
- PostgreSQL (recommended) or SQLite (quick local demo)
- Bootstrap 5

## Quick start (Windows PowerShell)

1. Install Python 3.10+ and PostgreSQL (or use SQLite for a quick first run).
2. Extract this ZIP and open the `subscript_mvp` folder in VS Code.
3. Create and activate a virtual environment:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. Copy `.env.example` to `.env`.

For PostgreSQL, create a database named `subscript_db`, then set `DATABASE_URL` in `.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/subscript_db
SECRET_KEY=replace-with-a-long-random-secret
SEED_DEMO=1
```

For a quick SQLite test, omit `DATABASE_URL`; the app creates `instance/subscript.db`.

5. Run:

```powershell
python app.py
```

6. Open http://127.0.0.1:5000

## Demo admin
- Email: `admin@subscript.local`
- Password: `Admin@12345`

Change the demo password and SECRET_KEY before any shared/public deployment.

## Included workflows
- Customer self-registration with password complexity checks and unique email.
- Admin, staff and customer roles; only admin can create staff.
- Product creation and a product variant with additional price.
- Plans with daily/weekly/monthly/yearly frequency, minimum quantity, availability, tax rate and lifecycle permissions.
- Subscription creation and lifecycle status changes.
- Invoice generation for active subscriptions whose next billing date is due.
- Unique subscription + billing period constraint to prevent duplicate invoices.
- Fixed and percentage discount rules, dates, product targeting, minimum quantity and usage limits.
- Payment records against invoices, partial payments and overpayment prevention.
- Admin dashboard with active subscriptions, received revenue, outstanding balance and overdue invoices.
- Customer portal for own subscriptions and invoices.
- Quotation template records.

## Important demo notes / known limitations
- Password reset is a placeholder demonstration; actual email delivery requires configuring an email provider.
- Payments are manually recorded; no payment gateway is integrated.
- Invoice generation is triggered by the "Generate due invoices" button; production recurring scheduling needs a background scheduler.
- Quotation templates can be stored, but a complete quote-to-subscription workflow and quote PDF are not included.
- Product variant form supports one initial variant per product; extend as needed.
- The app is a hackathon MVP, not production-ready. Before public deployment add CSRF protection, secure session/cookie settings, migrations, audit logs, stronger validation, transaction/concurrency handling and automated tests.
- For a real multi-line invoice implementation, add subscription_items and invoice_items tables.

## GitHub
Do not commit `.env`, passwords, or secret keys. Commit `.env.example` instead.
