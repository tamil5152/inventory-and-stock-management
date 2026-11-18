# StockFlow: inventory and stock management

A Flask web app for a **computer accessories store**: products, shelves, staff, suppliers and stock levels. Staff count shelves with a
barcode scanner, and StockFlow **tells them which products need a physical check**: when stock
runs low, when a count does not match the system, or when a product is due for its cycle count.
Staff get in-app and desktop notifications, plus e-mail if you configure it.

![Dashboard](docs/screenshots/dashboard.png)

| Stock checks, assigned by shelf | Shelves and who looks after them |
|---|---|
| ![Stock checks](docs/screenshots/stock-checks.png) | ![Shelves](docs/screenshots/shelves.png) |

| Adding a staff member | Scan & count from a check |
|---|---|
| ![Add staff](docs/screenshots/add-staff.png) | ![Scan and count](docs/screenshots/scan-and-count.png) |

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

This creates 6 shelves, 3 suppliers, 15 computer-accessory products with two weeks of stock
history and shelf counts, the first round of stock checks, and these logins:

| Role    | Name          | Username  | Password         | Shelves |
|---------|---------------|-----------|------------------|---------|
| Admin   | Tamil Selvan  | `admin`   | `Admin@123456`   | (uses `ADMIN_EMAIL` as its e-mail) |
| Manager | Meena Raj     | `manager` | `Manager@123456` | |
| Staff   | Karthik Kumar | `staff`   | `Staff@123456`   | A1 Keyboards & Mice, A2 Monitors |
| Staff   | Priya Nair    | `priya`   | `Staff@123456`   | B1 Cables & Adapters, B2 Storage |
| Staff   | Arun Prakash  | `arun`    | `Staff@123456`   | C1 Audio, C2 Networking & Power |

The demo staff have made-up `@stockflow.local` addresses. Change them to real ones on the
**Staff** page (or add your real staff) so they receive the job e-mails.

> Already have an older database with stationery/hardware demo data? Delete
> `instance/inventory.db` and run `python seed_demo.py` again to get the computer-accessories catalogue.

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

63 tests cover risk scoring and automatic assignment, shelves, staff details, job e-mails, the stock-check alerts and notifications, the DSA utilities, login, permissions, products, stock movements, scanning,
suppliers, users and report exports. Tests use an in-memory database and do not touch your data.

---

## 6. Shelves, staff and job e-mails

**Shelves** (sidebar → *Shelves*) are where products are kept, e.g. `A1 Keyboards & Mice, Aisle A`.
Every product can be placed on a shelf (Products → Edit → *Shelf*).

**Adding a staff member** (sidebar → *Staff* → *Add staff member*, admin only) asks for:

- **Full name**, **e-mail** and **mobile number** (validated in the browser and again on the server)
- **Role**: staff, manager or admin
- **Shelves this person looks after** (tick one or more)
- Username and a temporary password (given in person; passwords are never e-mailed)

When a product needs a physical count, the check goes to **the least busy person assigned to
that product's shelf**. If nobody is assigned to the shelf, it goes to any staff member.

Who gets what:

| Event | Staff member | Admin mailbox (`ADMIN_EMAIL`) |
|---|---|---|
| New staff member added | Welcome e-mail with their shelves | Copy with name, e-mail, mobile, shelves |
| Shelf added to a staff member | In-app + e-mail | |
| Stock check assigned (stock-out, manual request) | In-app + e-mail with product, shelf, due time and a link that opens the scanner | **"New job assigned"** e-mail: product, shelf, assignee name, e-mail and mobile |
| Hourly automatic scan | In-app + e-mail per check | One digest e-mail listing all new jobs |
| Check reassigned | New assignee: in-app + e-mail | "Job reassigned" e-mail |
| Check overdue | In-app + e-mail | "Job overdue" e-mail |

The *Staff* page shows whether e-mail is on and has a **Send test e-mail** button.

## 7. Automatic, risk-based assignment

Every stock check gets a **risk score from 0 to 100** that says how likely the shelf is wrong
and how much it matters. The score is built from:

| Factor | Points |
|---|---|
| Out of stock, or at/below the reorder level | up to 40 |
| Selling fast: fewer than 3 or 7 days of stock left (sales over the last 14 days) | up to 20 |
| Last count did not match and nothing has changed since | up to 30 |
| Never counted, or past its count cycle | up to 20 |
| Stock value on the shelf (Rs. 5,000+ / Rs. 20,000+) | up to 10 |

The score sets the **priority** (70+ high, 40+ medium) and **due time** (8 h / 24 h / 3 days).
Any product at or above `ALERT_RISK_THRESHOLD` (default 60) gets a check even when nothing else triggered one.

**Who gets the job** is decided automatically:

1. **Shelf team first**: the staff who look after the product's shelf. If nobody does, all staff, then managers.
2. **Accuracy for risky jobs**: each person's share of correct counts over the last 60 days
   (new staff start at 90%). The higher the risk, the more accuracy counts.
3. **Fair workload**: the risk scores of the jobs each person already has are added up, so a
   person with two urgent jobs is not handed a third while a colleague is free.
4. **Second opinion on mismatches**: when a count does not match, a **recount is assigned
   immediately to a different person**. If the recount also does not match, managers and the admin
   mailbox get a "Recount confirms mismatch" alert to investigate.
5. **Overdue urgent jobs move on**: a high-priority job not done in time is **reassigned automatically**
   to the next best person (once), and the new person, the previous person and the admin are e-mailed.

The assigned person is **e-mailed automatically** with the product, shelf, risk score, why it needs
counting and why they were chosen. The same details appear on the *Stock checks* page.
This runs on its own: instantly when stock drops or a count is recorded, and every
`ALERT_INTERVAL_MINUTES` (default 60) while `python run.py` is running.

## 8. Gmail setup (send job e-mails)

The app sends mail through your Gmail account. Gmail does **not** accept your normal password
from apps; you need an **App Password**.

1. Sign in to the Gmail account that will send the mails (e.g. `t2064585@gmail.com`).
2. Open <https://myaccount.google.com/security> and turn on **2-Step Verification**
   (App Passwords only appear after this is on).
3. Open <https://myaccount.google.com/apppasswords>, type a name such as `StockFlow`, and click **Create**.
4. Google shows a 16-letter password like `abcd efgh ijkl mnop`. Copy it (spaces don't matter).
5. Open the `.env` file in the project folder and fill in:

```ini
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=t2064585@gmail.com
MAIL_PASSWORD=abcdefghijklmnop
MAIL_FROM=t2064585@gmail.com
ADMIN_EMAIL=t2064585@gmail.com
APP_BASE_URL=http://127.0.0.1:5000
DISPLAY_TIMEZONE=Asia/Kolkata
```

6. Stop the app (`Ctrl + C`) and start it again with `python run.py`. `.env` is only read at start-up.
7. Log in as admin → **Staff** → **Send test e-mail**. You should receive it within a minute
   (check Spam the first time and mark it *Not spam*).

| Setting | What it is |
|---|---|
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS` | Gmail's outgoing mail server. Keep these exactly as shown |
| `MAIL_USERNAME` | The Gmail address that logs in to send mail |
| `MAIL_PASSWORD` | The 16-letter **App Password**, not your Gmail password |
| `MAIL_FROM` | The "From" address on every e-mail (use the same Gmail address) |
| `ADMIN_EMAIL` | Mailbox that receives a copy of every job assignment and new-staff notice |
| `APP_BASE_URL` | Used to build the links inside e-mails. Change it when you host the app online |
| `DISPLAY_TIMEZONE` | Time zone for due times in e-mails |
| `ALERT_RISK_THRESHOLD` | Risk score (0-100) at which a product gets a check automatically. Default 60 |
| `AUTO_REASSIGN_OVERDUE` | `True` moves overdue high-priority jobs to the next best person |

Keep `.env` private. It is listed in `.gitignore`, so it is never pushed to GitHub.
If you think the App Password leaked, delete it on the App Passwords page and create a new one.

## 9. Stock-check alerts and notifications

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

### Running the scan from cron (production)

If you run several gunicorn workers, set `ALERT_SCHEDULER=False` and schedule this command instead:

```bash
flask --app run run-alerts      # e.g. hourly via cron or Windows Task Scheduler
```

## 10. Features

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
| **Shelves** | Shelf cards with location, product count and assigned staff; managers add and edit shelves |
| **Staff** (admin) | Add staff with name, e-mail, mobile and shelves; change roles and shelves, reset passwords, disable accounts; e-mail status and test e-mail |

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

## 11. Project structure

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
├── specs/               # feature design notes
├── tests/               # pytest suite
└── app/
    ├── __init__.py      # app factory, blueprints, error handlers, CLI
    ├── extensions.py    # db, login manager, CSRF
    ├── seed.py
    ├── models/          # User, Product, Supplier, Inventory, StockMovement, StockVerification,
    │                    #   AuditLog, CheckTask, Notification, Shelf
    ├── repositories/    # database queries
    ├── scheduler.py     # background stock-check scan
    ├── schema.py        # adds new columns to older databases automatically
    ├── services/        # business logic (inventory, verification, risk, priority, reports,
    │                    #   assignment_service: risk scores + choosing the right person,
    │                    #   recommendations, stock checks, notifications)
    ├── routes/          # auth, pages, and JSON APIs (/api/...)
    ├── utils/           # validators, DSA, role decorator, audit helper
    ├── templates/       # Jinja HTML pages
    └── static/          # css, js, fonts (IBM Plex, bundled so it works offline)
```

## 12. Main API endpoints

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

GET    /api/shelves/                          list shelves with staff
POST   /api/shelves/  PUT /api/shelves/<id>   {code, name, location?, staff_ids[]}  (manager+)
POST   /api/shelves/<id>/toggle               (manager+)

GET    /api/users/email-status                (admin)
POST   /api/users/test-email                  {to?}  (admin)

GET/POST /api/suppliers/   PUT /api/suppliers/<id>   POST /api/suppliers/<id>/toggle
GET/POST /api/users/       PUT /api/users/<id>      {full_name, email, phone, role, shelf_ids[], ...}  (admin)
```

## 13. Optional: Flask CLI & production

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

## 14. Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'flask'` | Activate the venv first, then `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'app'` / `config` | Run commands from the project root folder (where `run.py` is), not from inside `app/` |
| "CSRF token missing" | Refresh the page (the session expired or the server restarted with a new SECRET_KEY) |
| Port 5000 already in use | Change the port in `run.py`, or on macOS turn off *AirPlay Receiver* |
| Camera button says not supported | Use Chrome/Edge; camera needs `localhost`/`127.0.0.1` or HTTPS. USB scanners and typing always work |
| `Gmail rejected the login` on test e-mail | `MAIL_PASSWORD` must be the 16-letter App Password, and 2-Step Verification must be on |
| Test e-mail says e-mail is not set up | Fill `MAIL_SERVER` and `MAIL_FROM` in `.env`, then restart `python run.py` |
| Staff don't get job e-mails | Their e-mail on the Staff page must be real, and the product must be on one of their shelves |
| Desktop alerts don't appear | Click *Turn on desktop alerts* and allow notifications in the browser. They only work on `localhost`/`127.0.0.1` or HTTPS |
| No stock checks appear | Run `python seed_demo.py` on a fresh database, or click *Scan for new checks* as a manager |
| `no such column: products.count_interval_days` | Restart the app; it adds new columns automatically on start-up |
| Forgot the admin password | Delete `instance/inventory.db` and run `python seed_demo.py` again (wipes data) |
