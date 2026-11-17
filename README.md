# StockFlow: inventory and stock management

A Flask web app for managing products, suppliers and stock levels. Staff count shelves with a
barcode scanner, and StockFlow **tells them which products need a physical check**: when stock
runs low, when a count does not match the system, or when a product is due for its cycle count.
Staff get in-app and desktop notifications, plus e-mail if you configure it.

![Dashboard](docs/screenshots/dashboard.png)

| Stock checks for staff | Scan & count from a check |
|---|---|
| ![Stock checks](docs/screenshots/stock-checks.png) | ![Scan and count](docs/screenshots/scan-and-count.png) |

**Stack:** Python, Flask, SQLAlchemy (SQLite or PostgreSQL), Flask-Login, Flask-WTF (CSRF), vanilla JS, ReportLab (PDF), pytest.

---

## 1. Requirements

- **Python 3.10 or newer** (tested on 3.13; works on 3.14)
- pip
- A modern browser (Chrome / Edge / Firefox)

Check your Python version:

```bash
python --version        # Windows
python3 --version       # macOS / Linux
```

---

## 2. Setup (first time only)

Open a terminal **inside the `inventory-stock-management` folder** (the one that contains `run.py`).

### Windows (PowerShell, also the VS Code terminal)

If you have never run a venv in PowerShell, allow local scripts once (type `Y` to confirm):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then:

```bat
git clone https://github.com/tamil5152/inventory-and-stock-management.git
cd inventory-and-stock-management
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

> PowerShell error "running scripts is disabled"? Run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` and then `venv\Scripts\Activate.ps1`

### macOS / Linux

```bash
git clone https://github.com/tamil5152/inventory-and-stock-management.git
cd inventory-and-stock-management
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then open `.env` and set `SECRET_KEY` to a long random value:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. Create users and sample data

**Option A – demo data (recommended for trying it out)**

```bash
python seed_demo.py
```

This creates 3 suppliers, 12 products with two weeks of stock history and shelf counts,
the first round of stock checks, and these logins:

| Role    | Username  | Password         |
|---------|-----------|------------------|
| Admin   | `admin`   | `Admin@123456`   |
| Manager | `manager` | `Manager@123456` |
| Staff   | `staff`   | `Staff@123456`   |

Running it again is safe – it never duplicates data.

**Option B – only your own admin account (empty database)**

```bash
python seed_admin.py
```

It asks for username, email and a password (min 12 characters).

---

## 4. Run the app

```bash
python run.py
```

Open **http://127.0.0.1:5000** and log in.

Stop the server with `Ctrl + C`. Next time you only need to activate the venv and run
`python run.py` again.

The database is a SQLite file at `instance/inventory.db`. Delete it to start fresh
(then run a seed script again).

---

## 5. Run the tests

```bash
python -m pytest -q
```

44 tests cover the stock-check alerts and notifications, the DSA utilities, login, permissions, products, stock movements, scanning,
suppliers, users and report exports. Tests use an in-memory database and do not touch your data.

---

## 6. Stock-check alerts and notifications

StockFlow creates a **stock check**, a request to physically count one product, when:

| Situation | Priority | Due |
|---|---|---|
| The system shows zero stock and nobody has counted it since it last moved | High | 8 hours |
| The last count did not match the system and was not fixed for a day | High | 8 hours |
| Stock is at or below its reorder level and has not been counted since it last moved | Medium | 1 day |
| The product has never been counted | Low | 3 days |
| The product's count cycle has passed (set per product, default 30 days) | Low | 3 days |
| A manager asks for a count | Chosen | Chosen |

How it reaches the staff:

1. **Instantly on stock-out.** When a sale takes a product down to its reorder level, a check is created at once.
2. **Every hour in the background** (`ALERT_INTERVAL_MINUTES`) the app scans all products. Managers can also click **Scan for new checks**.
3. Each check goes to the active **staff** member with the fewest open checks (managers if there are no staff).
4. That person gets a **notification**: the bell in the top bar, a badge on *Stock checks* in the sidebar, a pop-up toast,
   and a **desktop notification** if they turned on desktop alerts. With SMTP settings in `.env` they also get an **e-mail**.
5. They click **Count now**. The scanner opens with the barcode filled in, they count the shelf and enter the number.
   Recording the count **completes the check automatically**.
6. If the count does not match, **managers and admins are notified** and can apply the counted quantity in one click.
7. Checks past their due time send a one-time **overdue** notification to the staff member and the managers.

Managers can request a count, reassign a check, change its priority, or cancel it from the *Stock checks* page.

### E-mail (optional)

Add your SMTP details to `.env`. For Gmail, create an *App Password* under Google Account → Security:

```
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-16-character-app-password
MAIL_FROM=you@gmail.com
APP_BASE_URL=http://127.0.0.1:5000
```

Leave `MAIL_SERVER` empty to use only in-app and desktop notifications.

### Running the scan from cron (production)

If you run several gunicorn workers, set `ALERT_SCHEDULER=False` and schedule this command instead:

```bash
flask --app run run-alerts      # e.g. hourly via cron or Windows Task Scheduler
```

## 7. Features

| Page | What it does |
|------|--------------|
| **Dashboard** | Shelf-check banner, key figures, 14-day stock in/out chart, stock value by category, reorder suggestions, highest-risk products, latest movements |
| **Stock checks** | Your counting queue sorted by priority and due time, with Count now, I'm on it, and completed history. Managers can request, reassign and cancel checks |
| **Notifications** | Bell with unread count, pop-up toasts, optional desktop alerts and e-mail |
| **Products** | Search/filter, add, edit, archive/restore, delete (admin, only if no history), quick stock update per row |
| **Inventory** | Stock in, stock out, set exact count (adjustment), low-stock list, full movement history |
| **Scan & count** | Scan with a USB scanner (types + Enter), keyboard, or phone/laptop camera (Chrome/Edge). Blind count → verification with discrepancy and risk score 0–100. Managers can apply the counted quantity in one click. Duplicate scans in a session are detected. Unknown barcodes are logged for review |
| **Suppliers** | Add, edit, activate/deactivate suppliers, link them to products |
| **Reports** | Stock valuation by category, movement report with date/type filters, discrepancies, risk ranking, audit log (admin). Export stock CSV/PDF and movements CSV |
| **Users** (admin) | Create users, change roles, reset passwords, disable accounts |

### Roles

| Action | Staff | Manager | Admin |
|--------|:----:|:----:|:----:|
| View everything, stock in/out, scan & verify | ✅ | ✅ | ✅ |
| Do assigned stock checks, receive check notifications | ✅ | ✅ | ✅ |
| Add/edit/archive products & suppliers, adjust stock to exact count | | ✅ | ✅ |
| Request, reassign and cancel stock checks; get mismatch and overdue alerts | | ✅ | ✅ |
| Delete products, manage users, view audit log | | | ✅ |

### Data structures used (`app/utils/dsa.py`)

| Structure | Where it is used |
|-----------|------------------|
| HashSet (`DuplicateScanDetector`) | Detects duplicate scans in a scan session |
| Queue (`ScanQueue`) | FIFO processing of batch scans (`POST /api/scanning/batch`) |
| Max-heap (`StockPriorityHeap`) | Risk priority list on the dashboard, and choosing the most urgent stock checks first |
| Binary search | SKU lookup (`GET /api/products/sku/<sku>`) |
| Merge sort | Risk ranking report |
| HashMap (`BarcodeHashMap`) | Utility + tests |

### Risk score

- **Verification risk** (scanner): up to 50 points for the size of the discrepancy, 30 if stock is at/below the reorder level, 20 if stock is found when the system says zero.
- **Stock-level risk** (priority list): 90 when out of stock, 40–69 when at/below reorder level.
- Levels: `LOW` < 35 ≤ `MEDIUM` < 70 ≤ `HIGH`.

---

## 8. Project structure

```
inventory-stock-management/
├── run.py               # start the dev server
├── wsgi.py              # production entry (gunicorn)
├── config.py            # settings (reads .env)
├── seed_demo.py         # demo users + sample data
├── seed_admin.py        # create one admin interactively
├── requirements.txt
├── .env.example
├── instance/            # SQLite database lives here
├── tests/               # pytest suite
└── app/
    ├── __init__.py      # app factory, blueprints, error handlers, CLI
    ├── extensions.py    # db, login manager, CSRF
    ├── seed.py
    ├── models/          # User, Product, Supplier, Inventory, StockMovement, StockVerification,
    │                    #   AuditLog, CheckTask, Notification
    ├── repositories/    # database queries
    ├── scheduler.py     # background stock-check scan
    ├── schema.py        # adds new columns to older databases automatically
    ├── services/        # business logic (inventory, verification, risk, priority, reports,
    │                    #   recommendations, stock checks, notifications)
    ├── routes/          # auth, pages, and JSON APIs (/api/...)
    ├── utils/           # validators, DSA, role decorator, audit helper
    ├── templates/       # Jinja HTML pages
    └── static/          # css, js, fonts (IBM Plex, bundled so it works offline)
```

## 9. Main API endpoints

All return JSON and need a logged-in session (browser) plus the `X-CSRFToken` header for POST/PUT/DELETE.

```
GET    /api/products/?q=&category=&status=      list / search
POST   /api/products/                          create (manager+)
PUT    /api/products/<id>                      update (manager+)
POST   /api/products/<id>/archive | /restore   (manager+)
DELETE /api/products/<id>                      (admin, no history)
GET    /api/products/barcode/<code>  |  /sku/<sku>

POST   /api/inventory/stock-in | /stock-out    {product_id, quantity, notes?, reference_number?}
POST   /api/inventory/adjust                   {product_id, quantity}  (manager+)
GET    /api/inventory/movements?product_id=    |  /low-stock

GET    /api/scanning/lookup/<barcode>
POST   /api/scanning/verify                    {barcode, physical_quantity, force?}
POST   /api/scanning/batch                     {scans: [{barcode, physical_quantity}]}
POST   /api/scanning/session/reset
GET    /api/scanning/history?issues=1

GET    /api/reports/summary | stock | categories | movements | discrepancies | risk | audit
GET    /api/reports/export/stock.csv | stock.pdf | movements.csv

GET    /api/checks/?status=open|done&scope=mine|all
GET    /api/checks/summary
POST   /api/checks/                            {product_id, assigned_to?, priority?, note?}  (manager+)
PUT    /api/checks/<id>                        reassign / priority / note  (manager+)
POST   /api/checks/<id>/start | /cancel
POST   /api/checks/run                         scan now (manager+)

GET    /api/notifications/                     latest + unread count
POST   /api/notifications/<id>/read | /read-all

GET/POST /api/suppliers/   PUT /api/suppliers/<id>   POST /api/suppliers/<id>/toggle
GET/POST /api/users/       PUT /api/users/<id>      (admin)
```

## 10. Optional: Flask CLI & production

```bash
flask --app run seed-demo
flask --app run create-admin
flask --app run run-alerts
```

Production (Linux):

```bash
gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app
```

Set `FLASK_DEBUG=False`, a strong `SECRET_KEY`, and `COOKIE_SECURE=True` when served over HTTPS.
To use PostgreSQL, set `DATABASE_URL=postgresql://user:pass@host:5432/dbname` and `pip install psycopg2-binary`.

## 11. Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'flask'` | Activate the venv first, then `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'app'` / `config` | Run commands from the project root folder (where `run.py` is), not from inside `app/` |
| "CSRF token missing" | Refresh the page (the session expired or the server restarted with a new SECRET_KEY) |
| Port 5000 already in use | Change the port in `run.py`, or on macOS turn off *AirPlay Receiver* |
| Camera button says not supported | Use Chrome/Edge; camera needs `localhost`/`127.0.0.1` or HTTPS. USB scanners and typing always work |
| Desktop alerts don't appear | Click *Turn on desktop alerts* and allow notifications in the browser. They only work on `localhost`/`127.0.0.1` or HTTPS |
| No stock checks appear | Run `python seed_demo.py` on a fresh database, or click *Scan for new checks* as a manager |
| `no such column: products.count_interval_days` | Restart the app; it adds new columns automatically on start-up |
| Forgot the admin password | Delete `instance/inventory.db` and run `python seed_demo.py` again (wipes data) |
