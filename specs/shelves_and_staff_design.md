# Shelves, staff details and admin e-mail: design

## Requirements

1. The catalogue is a **computer accessories** store. Demo categories are
   Keyboards & Mice, Monitors, Cables & Adapters, Storage, Audio, Networking,
   Power & Charging and Laptop Accessories. Stationery and Hardware are removed.
2. Products sit on a **shelf** (e.g. `A1 Keyboards & Mice`). Staff are responsible
   for one or more shelves.
3. Adding staff captures **full name, e-mail, mobile number, role, shelves**,
   plus username and a temporary password for login. The new staff member gets
   a welcome e-mail listing their shelves.
4. When a stock check is created for a product, it is **assigned to a staff
   member responsible for that product's shelf** (least busy first). That
   person gets an in-app notification and an e-mail.
5. The **admin mailbox** (`ADMIN_EMAIL`, e.g. t2064585@gmail.com) receives an
   e-mail for every job assignment: product, shelf, assignee name, e-mail and
   mobile. Automatic scans send one digest e-mail instead of one per task.
6. Admins can send a **test e-mail** from the Users page to check SMTP settings.

## Acceptance criteria

- Creating staff without a valid name, e-mail or mobile number fails with a clear message.
- A low-stock check on a product on shelf A1 goes to a staff member assigned to A1.
- If nobody is assigned to the shelf, it goes to the least busy staff member, then managers.
- Admin receives an assignment e-mail (or digest) when SMTP is configured.
- Existing databases are upgraded in place (new columns and tables).

## Data model

| Table | Change |
|---|---|
| `shelves` | new: id, code (unique), name, location, is_active, created_at |
| `user_shelves` | new: user_id, shelf_id (many-to-many) |
| `users` | + full_name, + phone |
| `products` | + shelf_id (nullable FK) |

## API

| Method | Path | Role |
|---|---|---|
| GET | `/api/shelves/` | any signed-in user |
| POST / PUT | `/api/shelves/`, `/api/shelves/<id>` | admin, manager |
| POST | `/api/shelves/<id>/toggle` | admin, manager |
| POST / PUT | `/api/users/`, `/api/users/<id>` (+ full_name, phone, shelf_ids) | admin |
| POST | `/api/users/test-email` | admin |

## Security notes

- All new endpoints require login; writes are role-checked on the server.
- Input is validated on the server (name length, e-mail format, mobile `^\+?\d{10,15}$`
  after removing spaces and dashes, shelf ids must exist). The browser
  validates too, but the server never relies on it.
- Passwords are never e-mailed. The welcome mail contains only the username and sign-in link.
- SMTP credentials live in `.env`, which git ignores. Use a Gmail App Password, not the account password.
- Mobile numbers are only returned by the admin-only users API and on stock checks for managers.
- All values reach the page through `escapeHtml`, and Jinja auto-escapes.
- User creation, shelf changes and test mails are written to the audit log.
