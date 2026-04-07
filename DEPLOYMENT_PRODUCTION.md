# Alba Capital — Production Deployment Guide
Django 5.0.2 + Odoo 19 Enterprise + Bulk SMS

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Django Portal Deployment](#2-django-portal-deployment)
3. [Odoo 19 Addon Deployment](#3-odoo-19-addon-deployment)
4. [Post-Install Configuration](#4-post-install-configuration)
5. [SMS Provider Setup (alba_sms)](#5-sms-provider-setup-alba_sms)
6. [Django ↔ Odoo Integration Wiring](#6-django--odoo-integration-wiring)
7. [Production Hardening](#7-production-hardening)
8. [Cron Jobs Reference](#8-cron-jobs-reference)
9. [Environment Variable Reference](#9-environment-variable-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

### Server Requirements

| Component | Requirement |
|---|---|
| **Django server** | Ubuntu 22.04+, Python 3.12, Node.js 18+, Nginx, PostgreSQL 14+, SSL certificate |
| **Odoo server** | Ubuntu 22.04+, Odoo 19 Enterprise license, same or separate PostgreSQL instance |

Both servers must have outbound HTTPS access to SMS provider APIs and, where applicable, to each other. DNS must be configured for your domain(s) before running Certbot.

---

## 2. Django Portal Deployment

### 2.1 Server Setup

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv nginx postgresql-client
```

### 2.2 Clone & Install

```bash
git clone https://github.com/Kemboi14/Alba.git /opt/alba
cd /opt/alba
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2.3 Environment File

Create `/opt/alba/.env`:

```ini
SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_NAME=alba_production
DB_USER=alba_db_user
DB_PASSWORD=<strong-password>
DB_HOST=localhost
DB_PORT=5432
ODOO_URL=https://your-odoo-instance.com
ODOO_API_KEY=<from Odoo Alba Integration → API Keys>
ODOO_WEBHOOK_SECRET=<from Odoo Alba Integration → API Keys>
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### 2.4 Database & Static Files

```bash
python manage.py migrate
python manage.py collectstatic --no-input
python manage.py createsuperuser
```

### 2.5 Gunicorn systemd Service

Create `/etc/systemd/system/alba-django.service`:

```ini
[Unit]
Description=Alba Capital Django Portal
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/alba
EnvironmentFile=/opt/alba/.env
ExecStart=/opt/alba/venv/bin/gunicorn config.wsgi:application \
    --bind unix:/run/alba-django.sock \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/alba/gunicorn-access.log \
    --error-logfile /var/log/alba/gunicorn-error.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo mkdir -p /var/log/alba
sudo systemctl daemon-reload
sudo systemctl enable --now alba-django
```

### 2.6 Nginx Configuration

Create `/etc/nginx/sites-available/alba`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    client_max_body_size 50M;

    location /static/ {
        alias /opt/alba/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/alba/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://unix:/run/alba-django.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

Enable the site and obtain an SSL certificate:

```bash
sudo ln -s /etc/nginx/sites-available/alba /etc/nginx/sites-enabled/
sudo certbot --nginx -d yourdomain.com
sudo systemctl reload nginx
```

---

## 3. Odoo 19 Addon Deployment

### 3.1 Option A — Odoo.sh

1. Link your GitHub repository to your Odoo.sh project.
2. Set `odoo_addons/` as the custom addons path in the Odoo.sh project settings.
3. Push to your branch — Odoo.sh detects the new modules and rebuilds automatically.
4. Go to **Apps → Update App List**, then install modules in the order specified in Section 3.3.

### 3.2 Option B — Self-Hosted VPS

Copy the addons to your Odoo server:

```bash
# Copy addons to Odoo server
scp -r odoo_addons/* odoo-server:/opt/odoo/custom-addons/

# OR if same server
cp -r /opt/alba/odoo_addons/* /opt/odoo/custom-addons/
```

Update `/etc/odoo/odoo.conf` to include the custom addons path:

```ini
addons_path = /opt/odoo/addons,/opt/odoo/enterprise,/opt/odoo/custom-addons
```

Restart Odoo to pick up the new path:

```bash
sudo systemctl restart odoo
```

### 3.3 Install Order (Critical — Respect Dependency Chain)

In Odoo: **Settings → Apps → Update App List**, then install in this exact order:

1. `alba_loans` — no dependencies
2. `alba_investors` — depends on `alba_loans`
3. `alba_integration` — depends on `alba_loans` + `alba_investors`
4. `alba_sms` — depends on `alba_loans` + `alba_investors`

> ⚠️ Never install `alba_sms` before `alba_loans` and `alba_investors` — Odoo will refuse the installation due to unresolved dependencies.

---

## 4. Post-Install Configuration

### 4.1 Loan Products

Navigate to **Alba Loans → Configuration → Loan Products** and create at minimum:

- **Salary Advance** — flat rate, 1–6 month tenures
- **Business Loan** — reducing balance, 6–60 month tenures

Set accounting accounts on each product: Loan Receivable, Interest Income, Fees Income, and Penalty Income. These mappings are required before any loan can be disbursed.

### 4.2 Collection Stages

Navigate to **Alba Loans → Configuration → Collection Stages** — four default stages are seeded at install:

| Stage | Days Overdue | Default SMS |
|---|---|---|
| Reminder | 1–30 days | Yes |
| Collections | 31–60 days | Yes |
| Recovery | 61–90 days | Yes |
| Legal | 90+ days | Yes |

Edit the **SMS Template** field on each stage to customise the message that Alba SMS will send when a borrower enters that stage.

### 4.3 Integration API Key

Navigate to **Alba Integration → Configuration → API Keys → New**:

1. Enter a descriptive label (e.g. "Django Portal – Production").
2. Enter the Django portal base URL.
3. Click **Save** — the API Key and Webhook Secret are auto-generated.
4. Copy the **Key** and **Webhook Secret** and paste them into the Django `.env` file as `ODOO_API_KEY` and `ODOO_WEBHOOK_SECRET` respectively.

### 4.4 Assign User Groups

Navigate to **Settings → Users** and assign each staff member to the appropriate Odoo security group:

| Module | Available Groups |
|---|---|
| `alba_loans` | Loan Officer, Loan Manager, Director |
| `alba_integration` | Integration User, Integration Admin |
| `alba_sms` | SMS User, SMS Officer, SMS Admin |

Users should be assigned the minimum group necessary for their role.

---

## 5. SMS Provider Setup (alba_sms)

### 5.1 Add a Provider

Navigate to **Alba SMS → Configuration → SMS Providers → New** and fill in the following fields:

| Field | Description |
|---|---|
| Provider Type | Africa's Talking / Twilio / Vonage / Generic HTTP |
| API Endpoint URL | Your provider's send API URL |
| API Key | From your provider account dashboard |
| Sender ID | Short code or alphanumeric sender (e.g. `ALBA`) |

**Africa's Talking example:**
- URL: `https://api.africastalking.com/version1/messaging`
- Username: your AT username
- API Key: your AT API key
- Sender ID: your registered short code

**Generic HTTP example** (for any other Kenyan SMS gateway):
- Auth Type: API Key in Header
- Auth Header Name: `apiKey` (or whatever your provider requires)
- Phone Param Name: `to`
- Message Param Name: `message`
- Extra Params (JSON): `{"channel": "sms"}` (adjust to your provider's requirements)

### 5.2 Verify Templates

Navigate to **Alba SMS → Configuration → Message Templates** — eight default templates are seeded at install. Review and edit the content of each template to match Alba Capital's tone and regulatory requirements. All templates use `{placeholder}` syntax; available placeholders are listed on each template's form view.

### 5.3 Enable SMS

SMS is enabled by default after install. To disable it without uninstalling the module:

**Settings → Technical → Parameters → System Parameters** → find `alba_sms.enabled` → set the value to `0`.

To re-enable, set the value back to `1`.

### 5.4 DLR Webhook (Delivery Receipts) — Optional

If your SMS provider supports delivery receipt callbacks, configure the DLR callback URL in your provider's dashboard as follows:

**Generic DLR endpoint:**
```
https://your-odoo-instance.com/alba/sms/dlr
```

**Africa's Talking-specific endpoint:**
```
https://your-odoo-instance.com/alba/sms/dlr/africa_talking
```

Delivery receipts are recorded in **Alba SMS → SMS Logs** and allow you to distinguish delivered messages from failed ones.

### 5.5 Dual-Notification Check

**Important:** Both `alba_integration` and `alba_sms` can fire on the same overdue, maturity, and payment events. Check whether your Django portal also sends customer notifications when it receives `loan.instalment_overdue` or `payment.matched` webhook payloads. If it does, you must disable the Django-side notification to avoid sending duplicate SMS messages to customers. See Section 10 (Troubleshooting) for resolution steps.

---

## 6. Django ↔ Odoo Integration Wiring

Verify end-to-end connectivity by running the following smoke tests immediately after deployment:

```bash
# 1. Health check
curl https://your-odoo-instance.com/alba/api/v1/health \
  -H "X-Alba-API-Key: <your-key>"
# Expected: {"status": "ok"}

# 2. Create a customer
curl -X POST https://your-odoo-instance.com/alba/api/v1/customers \
  -H "X-Alba-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Customer","email":"test@example.com","phone":"0712345678"}'
# Expected: {"id": <odoo_customer_id>}

# 3. Submit a loan application
curl -X POST https://your-odoo-instance.com/alba/api/v1/applications \
  -H "X-Alba-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"customer_id": <id>, "product_id": 1, "amount": 50000, "tenure_months": 12}'
# Expected: {"id": <application_id>, "state": "draft"}
```

All three requests must return HTTP 200 with the expected JSON body before you consider the integration live. If any request fails, consult Section 10 (Troubleshooting) before proceeding.

---

## 7. Production Hardening

| Item | Action |
|---|---|
| Django DEBUG | Set `DEBUG=False` in `.env` |
| SECRET_KEY | Minimum 50 characters; never use a default or committed value |
| HTTPS | Enforce via Nginx redirect (configured in Section 2.6) |
| Cookie security | `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True` |
| API Key IP allowlist | In Odoo: **Alba Integration → API Keys → Allowed IPs** — restrict to Django server IP |
| Odoo admin password | Change the default `admin` password immediately after first login |
| Firewall | Allow only ports 80 and 443 inbound; block port 8069 from the public internet |
| Log rotation | Configure logrotate for `/var/log/alba/` and the Odoo log directory |
| DB backups | `pg_dump` cron at 02:00 daily; store backup files on a separate server or object storage |

---

## 8. Cron Jobs Reference

### Odoo Crons (Auto-Enabled at Install)

| Cron | Frequency | Module |
|---|---|---|
| Update PAR Buckets | Daily | alba_loans |
| NPL Monitor (flag 90+ day loans) | Daily | alba_loans |
| Overdue Payment Alerts | Daily | alba_loans |
| Maturity Date Reminders | Weekly | alba_loans |
| Auto-close Fully-Repaid Loans | Daily | alba_loans |
| Query Pending STK Transactions | Every 30 min | alba_loans |
| Auto-reconcile M-Pesa | Hourly | alba_loans |
| Sync Portfolio Stats to Django | Every 6 hours | alba_loans |
| Collections Workflow | Daily | alba_loans |
| Monthly Interest Accrual | Monthly | alba_investors |
| Process Webhook Retry Queue | Every 15 min | alba_integration |
| Purge Old Sync Logs | Weekly | alba_integration |
| Integration Health Check | Every 6 hours | alba_integration |
| **Process Scheduled SMS Batches** | **Every 15 min** | **alba_sms** |

Manage, pause, or adjust all crons at: **Settings → Technical → Automation → Scheduled Actions**

---

## 9. Environment Variable Reference

| Variable | Required | Where | Description |
|---|---|---|---|
| `SECRET_KEY` | ✅ | Django `.env` | Django secret key — must be unique, random, and at least 50 characters |
| `DEBUG` | ✅ | Django `.env` | Must be `False` in production |
| `ALLOWED_HOSTS` | ✅ | Django `.env` | Comma-separated list of permitted domain names |
| `DB_NAME` | ✅ | Django `.env` | PostgreSQL database name |
| `DB_USER` | ✅ | Django `.env` | PostgreSQL user |
| `DB_PASSWORD` | ✅ | Django `.env` | PostgreSQL password |
| `DB_HOST` | ✅ | Django `.env` | Database host (default: `localhost`) |
| `DB_PORT` | ✅ | Django `.env` | Database port (default: `5432`) |
| `ODOO_URL` | ✅ | Django `.env` | Odoo base URL used for all API calls |
| `ODOO_API_KEY` | ✅ | Django `.env` | Generated in Odoo: **Alba Integration → API Keys** |
| `ODOO_WEBHOOK_SECRET` | ✅ | Django `.env` | Generated in Odoo: **Alba Integration → API Keys** |
| `SESSION_COOKIE_SECURE` | prod | Django `.env` | Set to `True` in production to enforce HTTPS-only cookies |
| `CSRF_COOKIE_SECURE` | prod | Django `.env` | Set to `True` in production to enforce HTTPS-only CSRF cookie |
| `alba_sms.enabled` | — | Odoo sys param | `1` = SMS enabled, `0` = SMS disabled |

---

## 10. Troubleshooting

### Django: 500 Errors on Startup

```bash
source venv/bin/activate && python manage.py check --deploy
```

The deploy check will surface missing environment variables and misconfigured settings. The application will fail fast on a missing `SECRET_KEY` or `DB_PASSWORD` — verify your `.env` file is present and readable by `www-data`.

### Odoo: Module Not Found After Copy

```bash
sudo systemctl restart odoo
# Then in Odoo: Settings → Apps → Update App List
```

If the module still does not appear, confirm that `custom-addons` is listed in `addons_path` inside `/etc/odoo/odoo.conf` and that the directory is readable by the `odoo` system user.

### alba_sms: SMS Not Sending

1. Confirm `alba_sms.enabled` system parameter is set to `1`.
2. Confirm at least one active provider exists: **Alba SMS → Configuration → SMS Providers**.
3. Inspect `alba.sms.log` for error messages: **Alba SMS → SMS Logs → Failed**.
4. Test provider connectivity directly from the provider form: click **Test Connection**.
5. If using Africa's Talking, verify your account has a non-zero airtime balance and that the Sender ID is approved.

### Webhooks Not Reaching Django

1. Check **Alba Integration → Webhook Logs** for HTTP error status codes.
2. Check **Alba Integration → Retry Queue** for stuck or repeatedly-failing records.
3. Verify that `ODOO_WEBHOOK_SECRET` in the Django `.env` matches the webhook secret shown on the Odoo API key record exactly — any whitespace difference will cause HMAC verification to fail.
4. Confirm Django's Nginx configuration is not blocking `POST` requests to the webhook endpoint.

### Duplicate SMS to Customers

If customers report receiving two SMS messages per event, the Django portal is also sending notifications on the same integration webhooks that `alba_sms` already handles. To resolve:

**Option A (recommended):** Edit the Django webhook handler to skip SMS dispatch when the incoming payload includes `"sms_sent_by_odoo": true`.

**Option B:** Disable Django-side SMS notifications entirely for the affected event types (`loan.instalment_overdue`, `payment.matched`, `loan.maturity_reminder`) and rely exclusively on `alba_sms` for customer-facing messages.