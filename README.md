# Clerq

Business financial tracking app with Plaid bank integration, Zelle detection, multi-organization support, and PDF receipt generation.

---

## Table of Contents

- [Local Development](#local-development)
- [Production Deployment (Hostinger VPS)](#production-deployment-hostinger-vps)
- [Environment Variables](#environment-variables)
- [Architecture](#architecture)

---

## Local Development

### Prerequisites
- Docker Desktop
- A [Plaid developer account](https://dashboard.plaid.com) (free sandbox)

### Setup

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd TBK-biz-tracking

# 2. Create your .env file
cp .env.example .env
# Edit .env — fill in SECRET_KEY, PLAID_CLIENT_ID, PLAID_SECRET

# 3. Build and start all services
docker compose up --build

# App runs at:
#   Frontend  → http://localhost:3000
#   Backend   → http://localhost:8000
#   API docs  → http://localhost:8000/docs
```

### Plaid sandbox test credentials
In the Plaid Link modal, use:
- Username: `user_good`
- Password: `pass_good`

---

## Production Deployment (Hostinger VPS)

### Do I need a domain?

**Yes.** A domain is required for two reasons:
1. HTTPS — Let's Encrypt cannot issue a TLS certificate for a bare IP address
2. Plaid production — Plaid requires HTTPS on a real domain for production access

Hostinger sells domains from ~$2–10/year. You can buy one at checkout and DNS auto-configures.

---

### Step 1 — Purchase a Hostinger VPS

1. Go to [hostinger.com](https://hostinger.com) → **VPS Hosting**
2. Choose a plan — **KVM 2** (2 vCPU, 8 GB RAM) is recommended minimum for this stack
3. Select **Ubuntu 22.04** as the OS
4. Optionally purchase a domain at the same time (e.g. `biztrackreceipts.com`)
5. Complete checkout — note your **server IP** and **root password** from the welcome email

---

### Step 2 — Point your domain to the server

In Hostinger's **hPanel → DNS Zone**, add or update these records:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `@` | `<your-server-IP>` | 3600 |
| A | `www` | `<your-server-IP>` | 3600 |

DNS propagation takes 5–30 minutes. You can verify with:
```bash
nslookup yourdomain.com
```

---

### Step 3 — SSH into your server

```bash
ssh root@<your-server-IP>
```

---

### Step 4 — Install Docker and Docker Compose

```bash
# Update packages
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose plugin
apt install -y docker-compose-plugin

# Verify
docker --version
docker compose version
```

---

### Step 5 — Install Caddy (reverse proxy + automatic HTTPS)

Caddy automatically obtains and renews Let's Encrypt certificates.

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install caddy -y
```

---

### Step 6 — Clone your repository onto the server

```bash
# Option A: from GitHub (recommended)
git clone https://github.com/<your-username>/<your-repo>.git /opt/biztrack
cd /opt/biztrack

# Option B: copy files via scp from your local machine
# scp -r . root@<server-IP>:/opt/biztrack
```

---

### Step 7 — Create the production .env file

```bash
cd /opt/biztrack
cp .env.example .env
nano .env
```

Fill in every value:

```env
SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
PLAID_CLIENT_ID=<from Plaid dashboard>
PLAID_SECRET=<your Plaid production secret>
PLAID_ENV=production
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

> **Important:** `NEXT_PUBLIC_API_URL` must match the API subdomain you configure in Caddy below.

---

### Step 8 — Create a production Docker Compose override

Create `/opt/biztrack/docker-compose.prod.yml`:

```bash
nano /opt/biztrack/docker-compose.prod.yml
```

Paste:

```yaml
version: "3.9"

services:
  db:
    environment:
      POSTGRES_PASSWORD: <strong-random-password>
    ports: []  # Don't expose DB port publicly

  backend:
    ports: []  # Caddy proxies — no need to expose directly
    environment:
      DATABASE_URL: postgresql://biztrack:<strong-random-password>@db:5432/biztrack
      ALLOWED_ORIGINS: https://yourdomain.com,https://www.yourdomain.com
    restart: unless-stopped

  frontend:
    ports: []
    environment:
      NEXT_PUBLIC_API_URL: https://api.yourdomain.com
    restart: unless-stopped
```

> Replace `<strong-random-password>` with the same value in both places. Replace `yourdomain.com` with your actual domain.

---

### Step 9 — Configure Caddy

```bash
nano /etc/caddy/Caddyfile
```

Replace the contents with:

```
yourdomain.com, www.yourdomain.com {
    reverse_proxy localhost:3000
}

api.yourdomain.com {
    reverse_proxy localhost:8000
}
```

Restart Caddy:

```bash
systemctl restart caddy
systemctl enable caddy
```

Caddy automatically obtains HTTPS certificates from Let's Encrypt. Within a minute, `https://yourdomain.com` and `https://api.yourdomain.com` will be live.

---

### Step 10 — Add the API subdomain to DNS

Back in Hostinger hPanel → DNS Zone, add:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `api` | `<your-server-IP>` | 3600 |

---

### Step 11 — Start the application

```bash
cd /opt/biztrack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Check that all services are running:

```bash
docker compose ps
docker compose logs -f backend
```

Visit `https://yourdomain.com` — you should see the Clerq login page served over HTTPS.

---

### Step 12 — Configure Plaid for production

1. Log into the [Plaid Dashboard](https://dashboard.plaid.com)
2. Go to **Team Settings → API** → switch to **Production** environment
3. Under **Allowed redirect URIs**, add:
   ```
   https://yourdomain.com
   https://api.yourdomain.com/bank/connect
   ```
4. Submit your app for production review (Plaid requires this before live bank connections work)

---

### Step 13 — Keep the app updated

When you push code changes:

```bash
cd /opt/biztrack
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

---

### Useful commands on the server

```bash
# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Restart a single service
docker compose restart backend

# Connect to the database
docker compose exec db psql -U biztrack -d biztrack

# Stop everything
docker compose down

# Stop and delete all data (destructive!)
docker compose down -v
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing key — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `PLAID_CLIENT_ID` | Yes | From Plaid dashboard |
| `PLAID_SECRET` | Yes | Sandbox or production secret from Plaid dashboard |
| `PLAID_ENV` | Yes | `sandbox` or `production` |
| `NEXT_PUBLIC_API_URL` | Yes | Full URL of the backend API (e.g. `https://api.yourdomain.com`) |

---

## Architecture

| Service | Port (local) | Description |
|---|---|---|
| Frontend | 3000 | Next.js 14, TypeScript, Tailwind CSS |
| Backend | 8000 | FastAPI, Python 3.12, AsyncPG |
| Database | 5444 (external) | PostgreSQL 16 |

In production, Caddy sits in front and handles HTTPS — no ports are exposed directly.

### Key features
- **Plaid integration** — connect real bank accounts, sync transactions
- **Zelle detection** — auto-identifies Zelle transfers with direction and counterparty
- **PDF receipts** — per-transaction and batch export
- **Multi-organization** — separate books per business entity
- **Role-based access** — admin (full access) and viewer (read-only) roles
- **Invite links** — share access via time-limited invite URLs, no email server required
- **2FA** — optional TOTP (Google Authenticator) on every account
