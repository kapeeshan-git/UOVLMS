# University of Vavuniya — Library Management System (UOVLMS V2)

An integrated **Library Management System (ULMS)** for the **University of Vavuniya**, built with a separate **`backend/` (Django 5.2 + MySQL 8.x)** and **`frontend/` (React 19 + Vite + Tailwind CSS v4)** that operate together as a **single unified website** across localhost and your local network (LAN / Wi-Fi).

---

## 1. Repository Structure

```text
UOVLMS_V2/
├── README.md
├── db/
│   └── init/
│       └── 01_schema_and_users.sql         # Run once in MySQL Workbench (creates lms & test_lms)
├── backend/                                # Django 5.2 REST API + Table-Backed Worker
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── .env
│   ├── config/                             # settings.py, urls.py, api_urls.py, wsgi.py
│   ├── apps/
│   │   ├── core/                           # Controllable demo clock, errors, idempotency, middleware
│   │   ├── accounts/                       # Users, roles (ADMIN, LIBRARIAN, MEMBER), patron CRUD
│   │   ├── catalog/                        # Books, authors, categories, collections, copies, FULLTEXT ngram search
│   │   ├── circulation/                    # Issue, return, renew, fines ledger, rules, closed-day calendar
│   │   ├── notifications/                  # Table-backed Job queue (SKIP LOCKED) & scheduler (GET_LOCK)
│   │   ├── audit/                          # Append-only AuditEvent trail
│   │   ├── imports/                        # CSV dry-run validation & transactional apply
│   │   └── demo/                           # seed_demo management command (41 books, 107 copies, 8 users)
│   └── tests/                              # Automated business, concurrency & security test suite
└── frontend/                               # React 19 + Vite + Tailwind CSS v4 Single Website
    ├── package.json
    ├── vite.config.js                      # Binds 0.0.0.0:5173 and proxies /api to http://127.0.0.1:8000
    ├── public/                             # University of Vavuniya logos & icons
    └── src/
        ├── App.jsx                         # Unified routes, role guards & University footer
        ├── index.css                       # Vavuniya Maroon (#670047) & Gold (#ffcb00) theme
        ├── services/
        │   └── api.js                      # Unified API adapter (/api/v1 + CSRF + Idempotency-Key)
        ├── context/
        │   └── AuthContext.jsx             # Session authentication & role context
        ├── components/
        │   ├── layout/Navbar.jsx           # Two-tier official vau.ac.lk header & navigation bar
        │   ├── catalog/BookFormModal.jsx   # Multi-copy bibliographic & barcode editor
        │   ├── common/QrBarcodeScanner.jsx # Webcam & USB QR/Barcode scanner modal
        │   └── admin/                      # OverviewTab, BackupsTab, CustomFieldsTab
        └── pages/
            ├── HomePage.jsx                # Federated search, service tiles, trending books, collections
            ├── CatalogPage.jsx             # OPAC search, discipline filters, popularity sort, holds
            ├── CirculationDeskPage.jsx     # Koha-matched Check Out, Check In, Hold Shelf, Overdues, Rules
            ├── PatronDashboardPage.jsx     # Active loans, online renewals, holds, fines & alerts
            ├── AdminDashboardPage.jsx      # Analytics, Catalog, Patrons, CSV Import, Fines, Backups
            ├── RepositoryPage.jsx          # Institutional Digital Repository & peer review
            ├── EBooksPage.jsx              # Open-access textbooks & DOAB/OpenStax gateways
            ├── PublicationsPage.jsx        # University journals (VJBS, JST) & past papers
            ├── ServicesPage.jsx            # Borrowing rules, Turnitin, ISBN, ILL services
            ├── AboutPage.jsx               # Library history, hours, vision & mission
            └── LoginPage.jsx               # Patron & Staff login with 1-click role testing
```

---

## 2. Database Setup (Local MySQL Server + MySQL Workbench on Windows)

### Option A: Local MySQL 8.x + MySQL Workbench (Recommended for Production / Concurrency)

1. **Start MySQL Server** on Windows:
   - Open **Services** (`services.msc`) -> start **`MySQL80`**, or run in an **Administrator PowerShell**:
     ```powershell
     Start-Service MySQL80
     ```
2. **Create Schema & User in MySQL Workbench**:
   - Connect to `127.0.0.1:3306` as `root`.
   - Open [`db/init/01_schema_and_users.sql`](./db/init/01_schema_and_users.sql) and click **Execute (⚡)**.
   - This creates the `lms` and `test_lms` schemas (`utf8mb4` / `utf8mb4_0900_ai_ci`) and the `lms` user (`password: lms1234`).
3. Ensure [`backend/.env`](./backend/.env) has:
   ```env
   DB_ENGINE=mysql
   DB_NAME=lms
   DB_USER=lms
   DB_PASSWORD=lms1234
   DB_HOST=127.0.0.1
   DB_PORT=3306
   ```

### Option B: Instant Local SQLite Mode (Zero-Config Fallback)

If `MySQL80` is stopped and you want to run or test immediately without a database server:
```powershell
$env:DB_ENGINE="sqlite"
```

---

## 3. Running the Project (Localhost & Local Network / Wi-Fi)

### Step 1: Migrate, Seed & Start the Backend (`backend/`)

Open **Terminal 1** in `backend/`:

```powershell
cd c:\Users\kapee\Desktop\UOVLMS_V2\backend

# Activate virtual environment (or create one with: python -m venv .venv)
c:\Users\kapee\Desktop\UOVLMS\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Apply migrations & seed demo data (41 books, 107 copies, 8 users)
python manage.py migrate
python manage.py seed_demo

# Start Django bound to all network interfaces (0.0.0.0:8000)
python manage.py runserver 0.0.0.0:8000
```

*(Optional)* To run the background reminder scheduler & email worker in a separate terminal:
```powershell
python manage.py run_worker
```

### Step 2: Start the Frontend (`frontend/`)

Open **Terminal 2** in `frontend/`:

```powershell
cd c:\Users\kapee\Desktop\UOVLMS_V2\frontend

npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

---

## 4. Accessing the Website (Localhost & Local Network)

- **On the Host PC**:
  - **[http://localhost:5173/](http://localhost:5173/)** (Vite Dev Server with `/api` proxy)
  - **[http://localhost:8000/](http://localhost:8000/)** (Direct Django single-port server when `npm run build` has been run)
- **From Any Other Laptop, Tablet, or Phone on the Same Wi-Fi / LAN**:
  1. Find your PC's Wi-Fi IPv4 address (e.g., `10.125.129.227`) by running `ipconfig` in PowerShell.
  2. Open **`http://<YOUR-LAN-IP>:5173/`** (e.g. **[http://10.125.129.227:5173/](http://10.125.129.227:5173/)**) or **`http://<YOUR-LAN-IP>:8000/`** from any device on the network.
  3. Because [`frontend/vite.config.js`](./frontend/vite.config.js) proxies `/api` to `http://127.0.0.1:8000` with normalized `Origin` and `Referer` headers and [`backend/.env`](./backend/.env) sets `DJANGO_ALLOWED_HOSTS=*`, login sessions and CSRF tokens work seamlessly from any LAN device.
  4. *(Windows Firewall Tip)*: If another device on Wi-Fi cannot connect, ensure your Wi-Fi network profile is set to **Private network** or allow inbound TCP ports `5173` and `8000` in **Windows Defender Firewall**.

---

## 5. Demo Accounts & Fast Role Testing

On the **[Login Page (`/login`)](http://localhost:5173/login)**, you can use the **1-Click Fast Role Testing Buttons** (`Librarian`, `Admin`, `Lecturer`, `Student`) or sign in with any seeded account below (password for all seeded accounts: **`demo1234`**):

| Role | Username | Registration / Staff ID | Password | Highlights |
|---|---|---|---|---|
| **Librarian (Desk 1)** | `librarian1` *(or `librarian`)* | — | `demo1234` | Circulation Desk, Check Out, Check In, Overdues, Rules |
| **Librarian (Desk 2)** | `librarian2` | — | `demo1234` | Second desk for concurrency testing |
| **System Admin** | `admin` | — | `demo1234` | System Administration, Catalog, Patrons, CSV Import, Fines, Backups |
| **Student (Year 3)** | `student3` | `2024/ICT/014` *(or `2022/ICT/125`)* | `demo1234` | Stack limit: 4 books (has 2 active loans on seed) |
| **Student (Year 1)** | `student1` | `2026/ICT/001` | `demo1234` | Stack limit: 2 books |
| **Academic Lecturer** | `lecturer1` *(or `lecturer`)* | `STAFF/ACA/012` | `demo1234` | 30-day loan period, max 6 Stack books, Repository upload |
| **Non-Academic Staff** | `staff1` | `STAFF/ADM/045` | `demo1234` | Stack allowed (max 2); Reference borrowing blocked |
| **Graduating Student** | `grad1` | `2023/BIO/008` | `demo1234` | Has an open fine of **Rs. 40.00** (for fine settlement & clearance demo) |

### Sample Accession Barcodes for Circulation Desk Testing
- `A-000002`, `A-000003`, `A-000004`, `A-000005` — Available Lending Stack copies (*Introduction to Algorithms*)
- `A-000006` — **Single-copy rare book** (*Single Copy Rare Manuscript on Concurrency*) for simultaneous checkout testing
- `A-000023` — Reference section copy (1-day loan for students, blocked for non-academic staff)
- `A-000104`, `A-000105` — Permanent Reference copies (In-Library Use Only — blocked from checkout with `422 COPY_NOT_BORROWABLE`)
- `A-000001`, `A-000007` — Currently checked out to `student3` (`2024/ICT/014`) — ready to test **Check In (Return)** or **Renew**

---

## 6. Automated Tests & Production Build

### Run Backend Automated Tests
```powershell
cd c:\Users\kapee\Desktop\UOVLMS_V2\backend
c:\Users\kapee\Desktop\UOVLMS\.venv\Scripts\python.exe manage.py test tests
```

### Build Production Frontend Bundle
```powershell
cd c:\Users\kapee\Desktop\UOVLMS_V2\frontend
npm run build
```
When `npm run build` completes, the compiled assets are written to `frontend/dist/`, allowing Django (`http://0.0.0.0:8000`) to serve both the React website and `/api/v1/` from a single process.
