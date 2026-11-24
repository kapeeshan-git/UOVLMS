# University of Vavuniya: Library Management System (demo)

A lightweight circulation system built from [docs/demo-build-guide.md](docs/demo-build-guide.md), using **MySQL 8 + MySQL Workbench**.

**Why it is light:** two Python dependencies (`Django`, `mysqlclient`). There is no DRF, Celery, Redis, Docker or Node build step. The UI is plain HTML/CSS/JS (about 60 KB) served by Django. Background work is one extra process.

| Part | What it is |
|---|---|
| `config/` | Settings (with a built-in `.env` loader), URLs |
| `apps/core` | Clock (demo time travel), JSON API helpers, idempotency, request IDs, demo tools |
| `apps/accounts` | Users, roles, patrons, login, password reset |
| `apps/catalog` | Books, copies, collections, sections, FULLTEXT (ngram) search |
| `apps/circulation` | Rules, calendar, issue/return/renew/lost, fines ledger, clearance, reminders |
| `apps/notifications` | Table-backed job queue, email templates, `run_worker` |
| `apps/audit`, `apps/imports`, `apps/demo` | Audit log, CSV import with dry run, `seed_demo` |
| `frontend/` | `index.html`, `style.css`, `app.js` (no build) |
| `db/init/01_schema_and_users.sql` | Run once in MySQL Workbench |

## 1. Set up MySQL (once)

1. Start MySQL Server. Open **Services** as administrator and start `MySQL80`, or run `net start MySQL80` in an admin terminal.
2. In **MySQL Workbench**, connect as `root` and open [db/init/01_schema_and_users.sql](db/init/01_schema_and_users.sql). Change the password, then run it (⚡).

## 2. Configure and run

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # set DB_PASSWORD to the password you chose above
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo
```

Run two terminals:

```powershell
.\.venv\Scripts\python manage.py runserver        # app: http://127.0.0.1:8000
.\.venv\Scripts\python manage.py run_worker       # reminders + emails
```

**Demo logins** (password = `DEMO_PASSWORD`, default `demo1234`): `admin`, `librarian1`, `librarian2`, `student1` (year 1), `student3` (year 3), `lecturer1`, `staff1` (non-academic), `grad1` (has an open fine).

**Emails:** with `EMAIL_HOST` empty, emails are written to `var/mail/` and also appear in **Admin → Jobs & email**. Set `EMAIL_HOST` to use the university SMTP server.

**Reset demo data:** `python manage.py seed_demo --reset` (this wipes everything).

## 3. Tests

```powershell
.\.venv\Scripts\python manage.py test tests       # on MySQL: includes the real-thread concurrency tests
$env:DB_ENGINE="sqlite"; .\.venv\Scripts\python manage.py test tests   # quick logic run (concurrency tests skipped)
.\.venv\Scripts\python tests\smoke.py http://127.0.0.1:8000             # live check against a running server
```

## 4. Demo script (guide §15.2), about 10 minutes

1. Log in as `librarian1` and open **Desk**. Scan (type) `student3`, then the accession number of a Lending copy and press Enter.
2. Rule checks: a 5th Stack book is refused (`LOAN_LIMIT_REACHED`). A Permanent Reference copy is in-library use only. Issuing the same copy again fails because it is not available.
3. Concurrency: as `librarian2` in another browser, issue the single-copy book (*Introduction to Algorithms*) to two patrons at the same moment. Exactly one succeeds.
4. Log in as `admin` and open **Demo tools**. Move the clock forward. Within about 30 seconds the worker queues reminders; see them in **Jobs & email**.
5. Move past the due date and return the book. The fine counts open days only. In **Fines**, record a partial payment and a waiver with a reason.
6. Open `grad1`: clearance fails. Pay the fine; clearance passes, and you can set the status to Graduated.
7. Log in as `student3` to see own loans and fines, renew, and search.
8. Admin: **Audit** shows every step. **Demo tools → Simulate outage**, return a late book, watch the job retry, restore SMTP, then click **Retry**.
9. **Import**: upload [docs/sample_books_import.csv](docs/sample_books_import.csv) as a dry run to see the errors on rows 4 and 5. Delete those rows and apply.

## Production notes

Set `DJANGO_DEBUG=false`, a long random `DJANGO_SECRET_KEY` and `DEMO_CLOCK_ENABLED=false`. Serve with a WSGI server (`gunicorn`, or `waitress` on Windows) behind Nginx with HTTPS. Keep `run_worker` running as a service. Seeded passwords and demo tools are for demos only.
