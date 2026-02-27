# BizTrack Receipts — Complete Setup Guide

---

## What This Tool Does

BizTrack connects to your real business bank account via Plaid (the same
infrastructure used by Coinbase, Venmo, and thousands of fintechs), fetches
your transaction history, auto-detects Zelle transfers, categorizes all
spending, and generates downloadable PDF receipts.

- Zelle has no public API. This tool detects Zelle by parsing the transaction
  names your bank sends (e.g. "Zelle from john@gmail.com") and extracts the
  counterparty email or phone automatically.

---

## Prerequisites

Install these before starting:

| Tool        | Download                          | Check installed     |
|-------------|-----------------------------------|---------------------|
| Docker      | https://docker.com/get-started    | `docker --version`  |
| Docker Compose | Included with Docker Desktop   | `docker compose version` |
| Node.js 20+ | https://nodejs.org                | `node --version`    |
| Python 3.12+| https://python.org                | `python3 --version` |

---

## Step 1: Get Your Free Plaid API Keys (5 minutes)

Plaid is the bank connection layer. Sandbox is completely free and uses
test data. You do NOT need to connect a real bank to test.

1. Go to https://dashboard.plaid.com
2. Click "Get API Keys" and create a free account
3. After signing in, go to: Team Settings > Keys
4. You will see two values — copy both:
   - **Client ID** (looks like: 62f3a8b2c4d5e6f7a8b9c0d1)
   - **Sandbox secret** (looks like: abc123def456ghi789jkl012mno345pq)
5. Keep these ready for Step 3

> Note: Sandbox = fake test data. To use REAL bank transactions,
> you must apply for Plaid Production access (requires business
> verification at https://dashboard.plaid.com/overview/production).
> For personal/business internal use, sandbox works fine for testing
> the full flow.

---

## Step 2: Configure Environment Variables

In your project folder, create `backend/.env` from the template:

```bash
# Mac/Linux:
cp backend/.env.example backend/.env

# Windows:
copy backend\\.env.example backend\\.env
```

Open `backend/.env` in any text editor and fill in your Plaid keys:

```
SECRET_KEY=run-python3-c-import-secrets-print-secrets.token_hex-32-and-paste-here
PLAID_CLIENT_ID=your_client_id_from_step_1
PLAID_SECRET=your_sandbox_secret_from_step_1
PLAID_ENV=sandbox
```

Generate a SECRET_KEY by running:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and paste it as your SECRET_KEY in `backend/.env`.

---

## Step 3: Launch with Docker (Recommended)

This starts PostgreSQL, the Python backend, and the Next.js frontend
all at once.

```bash
# In the biztrack-receipts/ folder:
docker compose up --build
```

First build takes 3-5 minutes (downloads dependencies).

When you see:
```
backend  | INFO:     Application startup complete.
frontend | ready - started server on 0.0.0.0:3000
```

The app is running. Open: http://localhost:3000

---

## Step 4: Alternative — Run Without Docker

### Backend (Python/FastAPI)

```bash
cd backend

# Create virtual environment
python3 -m venv venv

# Activate it
# Mac/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the API server
uvicorn app.main:app --reload --port 8000
```

You also need PostgreSQL running locally. The easiest way:
```bash
# If you have Docker just for the DB:
docker run -d \
  --name biztrack-db \
  -e POSTGRES_USER=biztrack \
  -e POSTGRES_PASSWORD=biztrack_secret \
  -e POSTGRES_DB=biztrack \
  -p 5444:5432 \
  postgres:16-alpine
```

### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:3000

---

## Step 5: Create Your Account

1. Go to http://localhost:3000
2. Click "Register"
3. Enter your email and password
4. After registering, you'll see a **TOTP Secret** — this is for 2FA.
   - Optional: Scan it in Google Authenticator
   - If you skip 2FA, just leave the "2FA Code" field blank when logging in
5. Click "Sign In" and log in with your credentials

---

## Step 6: Connect Your Bank Account

### Sandbox (Test Mode)

1. On the dashboard, click **"Connect Bank Account"**
2. The Plaid Link modal will open
3. Search for any bank (e.g. "Chase")
4. Use these test credentials:
   - **Username:** `user_good`
   - **Password:** `pass_good`
5. Select any account type
6. Click **"Continue"**

This will connect a fake account with realistic transaction data
including some Zelle entries.

### Real Bank (Production Mode)

To connect your actual bank:

1. Apply for Plaid Production at: https://dashboard.plaid.com/overview/production
2. Plaid will review your application (usually 1-3 business days)
3. Once approved, update `backend/.env`:
   ```
   PLAID_ENV=production
   PLAID_SECRET=your_production_secret_here
   ```
4. Restart: `docker compose down && docker compose up`
5. Connect your bank normally through the Plaid modal

Supported banks include: Chase, Bank of America, Wells Fargo, Citi,
Capital One, US Bank, TD Bank, and 10,000+ others.

---

## Step 7: Sync and View Transactions

1. Click **"Sync (90 days)"** — this fetches the last 90 days of transactions
2. Wait 5 seconds, then the page refreshes automatically
3. You'll see:
   - Color-coded summary cards (deposits, withdrawals, Zelle totals)
   - A transaction table with all entries
   - Zelle transactions flagged with the counterparty email/phone
   - Auto-categorized spending (Groceries, Gas, Utilities, etc.)

---

## Step 8: Download Receipts

**Single receipt:** Click "PDF" in the Receipt column for any transaction.

**Batch export:** Click "Export PDF" in the top bar to download all
current transactions as one PDF report.

You can filter by date range, type, Zelle-only, or category before
exporting to get exactly the period you need.

---

## Running Tests

```bash
cd backend

# With virtualenv active:
python tests/test_zelle_parser.py
python tests/test_categorizer.py

# Or with pytest:
pip install pytest
pytest tests/ -v
```

---

## API Documentation

FastAPI auto-generates interactive docs.

Open: http://localhost:8000/docs

You can test every endpoint directly in the browser — useful for
debugging or building integrations.

Key endpoints:
- POST `/auth/register` — create account
- POST `/auth/login` — get JWT token
- GET  `/bank/link-token` — get Plaid Link token
- POST `/bank/connect` — exchange Plaid token and store account
- POST `/transactions/sync` — fetch and store transactions from Plaid
- GET  `/transactions/` — list transactions with filters
- GET  `/receipts/{id}` — download single PDF receipt
- POST `/receipts/batch` — download batch PDF
- GET  `/totals/` — get financial summary
- GET  `/totals/monthly` — get month-by-month breakdown

---

## Deploying to the Cloud

### Option A: Render.com (Easiest, Free Tier Available)

1. Push your code to GitHub
2. Go to https://render.com and create an account
3. Create a **PostgreSQL** database (free tier)
4. Create a **Web Service** for the backend:
   - Root directory: `backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Add environment variables from `backend/.env`
5. Create a **Static Site** or **Web Service** for the frontend:
   - Root directory: `frontend`
   - Build command: `npm install && npm run build`
   - Start command: `npm start`
   - Set `NEXT_PUBLIC_API_URL` to your backend Render URL

### Option B: Heroku

```bash
# Install Heroku CLI: https://devcenter.heroku.com/articles/heroku-cli

# Backend
cd backend
heroku create biztrack-api
heroku addons:create heroku-postgresql:mini
heroku config:set PLAID_CLIENT_ID=xxx PLAID_SECRET=xxx SECRET_KEY=xxx
git push heroku main

# Frontend
cd frontend
heroku create biztrack-frontend
heroku config:set NEXT_PUBLIC_API_URL=https://biztrack-api.herokuapp.com
git push heroku main
```

### Option C: VPS (DigitalOcean, Linode, Hetzner)

```bash
# On your server:
git clone your-repo
cd biztrack-receipts
cp backend/.env.example backend/.env
# Edit backend/.env with your production values
docker compose up -d

# Set up Nginx reverse proxy for port 80/443
# Use Certbot for free SSL: https://certbot.eff.org
```

---

## Troubleshooting

**Backend won't start**
- Check container status: `docker compose ps`
- Check backend logs: `docker compose logs backend --tail=200`
- If logs show `ValidationError` for settings, ensure `backend/.env` exists and includes `SECRET_KEY`, `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`, and `ALLOWED_ORIGINS`
- Rebuild after config changes: `docker compose up --build -d`
- Verify API health: `curl -sS http://localhost:8000/health`

**Emergency reset (copy/paste)**
```bash
docker compose down
docker compose up --build -d
docker compose ps
docker compose logs backend --tail=100
curl -sS http://localhost:8000/health
```

**Hard reset (wipes local DB data)**
Use this only if normal reset fails and you are okay losing local PostgreSQL data.

```bash
docker compose down -v
docker compose up --build -d
docker compose ps
docker compose logs backend --tail=100
curl -sS http://localhost:8000/health
```

**"Failed to create link token"**
- Check your PLAID_CLIENT_ID and PLAID_SECRET in `backend/.env`
- Make sure PLAID_ENV matches the secret type (sandbox vs production)
- Restart containers after changing `backend/.env`

**"No connected bank accounts"**
- Complete Step 6 first before syncing

**Database connection errors**
- Make sure the `db` container is healthy: `docker compose ps`
- Wait 10 seconds after starting for the DB to be ready

**Frontend can't reach backend**
- Check `NEXT_PUBLIC_API_URL` is set to `http://localhost:8000`
- Make sure backend is running: visit http://localhost:8000/health

**Zelle not detected**
- Your bank uses a different Zelle description format
- Open an issue or add a custom keyword in `backend/app/services/zelle_parser.py`
- Look at what description Plaid returns in the `/transactions/` API response

**Port already in use**
```bash
# Kill the process on port 8000:
lsof -ti:8000 | xargs kill -9
# Kill the process on port 3000:
lsof -ti:3000 | xargs kill -9
```

---

## Security Notes

This is built for personal and internal business use. Before exposing
to the internet or multiple users:

1. Change SECRET_KEY to a unique random value
2. Set PLAID_ENV=production and apply for production access
3. Enable HTTPS (required by Plaid for production)
4. Consider encrypting the `plaid_access_token` column in the DB
5. This app does NOT store bank credentials — Plaid handles that securely
6. For compliance with financial regulations (PCI-DSS, FinCEN), consult a lawyer

---

## File Structure Summary

```
biztrack-receipts/
├── backend/
│   ├── .env.example            # Backend env template
│   ├── app/
│   │   ├── main.py              # FastAPI app, auth routes
│   │   ├── config.py            # Settings from .env
│   │   ├── database.py          # Async PostgreSQL connection
│   │   ├── models.py            # User, BankAccount, Transaction tables
│   │   ├── schemas.py           # Request/response validation
│   │   ├── auth.py              # JWT + 2FA
│   │   ├── routers/
│   │   │   ├── bank.py          # Plaid Link and account management
│   │   │   ├── transactions.py  # Sync and query transactions
│   │   │   ├── receipts.py      # PDF generation
│   │   │   └── totals.py        # Financial summaries
│   │   └── services/
│   │       ├── plaid_service.py # Plaid API wrapper
│   │       ├── zelle_parser.py  # Zelle detection logic
│   │       ├── categorizer.py   # Transaction categorization
│   │       └── pdf_generator.py # ReportLab PDF creation
│   └── tests/
│       ├── test_zelle_parser.py
│       └── test_categorizer.py
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── auth/page.tsx    # Login/Register
│       │   └── dashboard/page.tsx # Main dashboard
│       ├── components/
│       │   ├── PlaidLink.tsx    # Bank connection button
│       │   ├── SummaryCards.tsx # Financial totals
│       │   └── TransactionTable.tsx # Transaction list + PDF download
│       ├── lib/api.ts           # Axios API client
│       └── types/index.ts       # TypeScript types
├── docker-compose.yml
└── SETUP.md                     # This file
```
