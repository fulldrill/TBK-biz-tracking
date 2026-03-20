# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BizTrack is a full-stack fintech app for tracking business transactions. It connects to bank accounts via Plaid, auto-detects Zelle transfers, categorizes transactions, and generates PDF receipts.

## Commands

### Docker (primary workflow)
```bash
docker compose up --build          # Build and start all services
docker compose up -d --build       # Background mode
docker compose down                # Stop services
docker compose logs -f [service]   # Tail logs (service: db, backend, frontend)
```

### Backend (manual)
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Tests
pytest tests/ -v                   # All tests
pytest tests/test_zelle_parser.py  # Single test file
```

### Frontend (manual)
```bash
cd frontend
npm install
npm run dev    # Dev server on :3000
npm run build  # Production build
npm run lint   # ESLint
```

### API docs
```
http://localhost:8000/docs   # Swagger UI (interactive)
```

## Architecture

### Service Layout
- **Frontend** (Next.js 14, TypeScript, Tailwind) — port 3000
- **Backend** (FastAPI, Python 3.12, AsyncPG) — port 8000
- **Database** (PostgreSQL 16) — port 5444 external → 5432 internal

### Authentication Flow
1. Register → bcrypt password hash + TOTP secret generated → returns QR-code secret for Google Authenticator
2. Login → verifies password + optional TOTP code → returns JWT (HS256, 60-min expiry)
3. Frontend stores JWT in localStorage; Axios interceptor adds `Authorization: Bearer` header to all requests; 401 responses clear token and redirect to `/auth`

### Transaction Pipeline
1. `/transactions/sync` fetches raw Plaid data for all user bank accounts
2. `zelle_parser.py` detects Zelle transfers by matching transaction names/descriptions
3. `categorizer.py` applies rule-based categorization (Groceries, Gas, Utilities, etc.)
4. Deduplication via unique `plaid_transaction_id` before DB insert

### Database Models (`backend/app/models.py`)
- **users** — UUID PK, email, hashed_password, totp_secret
- **bank_accounts** — linked to user, stores Plaid access_token + account metadata
- **transactions** — linked to user + account, includes `is_zelle`, `zelle_counterparty`, `zelle_direction`, `receipt_path`

Tables are created at startup via SQLAlchemy ORM (no Alembic migration needed for fresh installs).

### Key Backend Files
- `app/main.py` — FastAPI app init, CORS config, startup hooks, auth routes
- `app/config.py` — Pydantic-settings env config
- `app/auth.py` — JWT + TOTP + bcrypt logic
- `app/routers/` — bank, transactions, receipts, totals
- `app/services/plaid_service.py` — Plaid API calls
- `app/services/pdf_generator.py` — ReportLab PDF creation (saved to `/app/receipts` volume)

### Key Frontend Files
- `src/lib/api.ts` — Axios client with JWT interceptors
- `src/app/dashboard/page.tsx` — Main UI; orchestrates account loading, sync, and export
- `src/components/PlaidLink.tsx` — Wraps react-plaid-link modal
- `src/types/index.ts` — Shared TypeScript interfaces

## Environment Variables

Copy `.env.example` to `.env` and fill in:
```
SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
PLAID_CLIENT_ID=<from Plaid dashboard>
PLAID_SECRET=<sandbox secret from Plaid dashboard>
PLAID_ENV=sandbox
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Docker Compose injects the rest (DATABASE_URL, ALLOWED_ORIGINS).

## Plaid Sandbox Testing

Use these test credentials in the Plaid Link modal:
- Username: `user_good`
- Password: `pass_good`

## Database Port

PostgreSQL is intentionally exposed on **5444** (not 5432) to avoid conflicts with local Postgres installs. Connection string: `postgresql://biztrack:biztrack_secret@localhost:5444/biztrack`
