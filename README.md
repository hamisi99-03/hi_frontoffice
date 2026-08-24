# MEATMAGIC

A standalone desktop point-of-sale application for the butcher shop front-office
sales sheet — same workflow (item → weight or amount paid → gross,
cash/mpesa/credit, expenses, credit ledger), but as a real app with a database
instead of one spreadsheet per day.

## What changed vs. the spreadsheet

- **No more monthly workbook / daily tabs.** Every sale and expense is just
  a database row tagged with a date. "Today's sheet" is really just
  "show me rows where date = today" — pick any date at the top of the page
  to view or add entries for that day, past or future.
- **WEIGHT / PAID (if unknown) / GROSS** work exactly like the spreadsheet:
  fill in one, the other is calculated. No circular references, no Table
  object naming issues — it's just server-side logic now.
- **Credit ledger carries a running balance across days automatically.**
  You can also now record part-payments (a customer paying down what they
  owe), which the spreadsheet couldn't really do cleanly.
- **Multiple people can use it at once** — each cashier logs in with their
  own account, and everything they enter is tagged with their name.
  The server uses Waitress (a threaded WSGI server) so multiple cashiers can
  add sales simultaneously without waiting for each other.

## First-time setup

### Option A — run the .exe (shop computer, no Python required)

1. Copy `MEATMAGIC.exe` to any folder on the shop computer.
2. Double-click it. The first launch creates the database, seeds the item
   list, and prints a one-time admin password — **write it down.**
3. From then on, just double-click `MEATMAGIC.exe` to start.

### Option B — run from source (development / customising)

Requires Python 3.10+ installed on the machine.

```bash
cd hi_frontoffice
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_items    # loads the starting item/price list
python manage.py createsuperuser   # create the owner/admin login
```

## Running it

```bash
python run_desktop.py
```

Opens MEATMAGIC in its own desktop window. Behind the scenes it starts a
threaded web server (Waitress) on `0.0.0.0:8000`, so **other computers on the
same shop WiFi/network can also use it from a normal web browser** at the LAN
address printed in the terminal. Each cashier just needs a browser — no Python
installed anywhere else.

To start the server alone without the desktop window (e.g. for headless
machines or testing), run:

```bash
python -c "from waitress import serve; import django; django.setup(); from frontoffice.wsgi import application; serve(application, host='0.0.0.0', port=8000, threads=10)"
```

## User roles

| Role | Can access | Can't access |
|---|---|---|
| **Cashier** (staff=False) | Today's Sales, Credit Ledger | Manage, /admin/ |
| **Manager** (staff=True) | Everything above + Manage pages | Only superusers can access /admin/ |
| **Owner** (superuser) | Everything, including Django /admin/ | — |

### Adding cashier accounts

As the owner, go to **Manage → Manage Users** and enter a username + password.
Cashiers are created with `is_staff=False`, keeping them out of management
pages. To make someone a manager, promote them via **/admin/** (Django admin).

## Day-to-day use

### Sales desk (`/` — Today's Sales)
- Add sales, expenses, and other services through the inline forms.
- Payment breakdown (cash/mpesa/credit) and net-cash figure update live.
- Use the date picker at the top to pull up, add to, or edit a different day.
- Use the **Show** filter dropdown to see only cash, mpesa, or credit sales.
- The **Sold Today** card at the bottom shows per-item totals for the day.

### Credit ledger (`/credit/`)
- Shows every customer's running balance across all credit sales.
- Search by customer name.
- Record part-payments or full settlements against any sale.

### Close day / printable summary
On the sales desk page, click the **Close Day** button at the bottom. This
reveals a full daily summary card with:
- Payment breakdown (cash, mpesa, credit, services)
- Total sales, expenses, net cash
- Stock remaining at close (opening → sold → remaining per item)

Click **Print** on that card for a cash-register-friendly end-of-day printout.
The print styles are built-in — the browser print dialog renders it as a clean
receipt without the UI chrome.

### Manage pages (`/manage/` — staff only)
| Page | What it does |
|---|---|
| **Items & Prices** | Add, edit, deactivate items in the price list |
| **Stock** | Set opening stock per item per day |
| **Browse Sales** | Search all sales by date range and payment type |
| **Browse Expenses** | Search expenses by date range |
| **Credit Payments** | Browse and search credit payment history |
| **Manage Users** | Add cashier accounts, delete users |
| **Reports** | Date-range reports with per-item totals and CSV export |

## Reports

Go to **Manage → Reports**. Choose a date range and click **Generate**.

The report shows:
- **Summary** — total sales broken down by payment method, plus services,
  expenses, and net cash.
- **Sales by Item** — every item's total kilograms sold, gross revenue,
  and average price per kg across the range (the old ITEM/PPKG table).

Two actions are available once a report is generated:
- **Download CSV** — exports every individual sale row in the range as a
  spreadsheet-ready CSV file (Date, Item, Weight, Gross, Payment, Customer,
  Cashier).
- **Print** — opens the browser print dialog; the built-in print styles
  remove navigation and buttons, producing a clean paper report.

## Building the .exe

From the `hi_frontoffice/` directory:

```bash
pip install pyinstaller
pyinstaller meatmagic.spec --clean
```

The output is `dist/MEATMAGIC.exe`. This single file bundles Python, Django,
Waitress, SQLite, the templates, and all static assets — it runs on any
Windows machine with nothing else installed. The database is created beside
the .exe on first launch.

## Backing up your data

Everything lives in one file: `db.sqlite3`. Copy it somewhere safe
periodically (a USB drive, cloud folder, etc.) — that one file is your
entire sales history. Also back up `meatmagic.key` if you want to preserve
the encryption secret.

## Security note

This is set up for **local shop-network use only** — `DEBUG=True` and open
`ALLOWED_HOSTS` make setup painless on a LAN but are not safe to expose
directly to the internet. If you ever want remote/off-site access, that
needs a proper deployment with HTTPS and a reverse proxy — happy to help
with that when you get there.

## Extending this

The code is organised as a standard Django app (`sales/models.py`,
`views.py`, `views_admin.py`, `forms.py`, `templates/sales/`). Things you
might add next:
- Export monthly P&L or cash-flow summaries
- Stock-take reconciliation (physical count vs. system)
- Supplier invoicing / purchase tracking
- SMS or WhatsApp receipts for credit customers
