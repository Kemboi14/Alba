# Alba Capital — Loan Management Platform

**Django 5.0.2 · Odoo 19 Enterprise · PostgreSQL · Python 3.12**

---

## Overview

Alba Capital is a two-system financial services platform:

| System | Technology | Responsibility |
|---|---|---|
| **Customer Portal** | Django 5.0.2 (this repo) | Public-facing loan applications, KYC, document upload, guarantors, loan tracking |
| **Staff Back-Office** | Odoo 19 Enterprise (`odoo_addons/`) | 4 custom addons — loan lifecycle, investor accounts, API bridge, bulk SMS |
| **Database** | PostgreSQL | Shared persistent store |

Customers register, complete their KYC profile, upload documents, add guarantors, apply for loans, and track their active loans entirely through the Django portal. All staff-side processing — credit review, approval, disbursement, repayment accounting, investor management, and collections — runs inside Odoo 19 Enterprise via four purpose-built addons.

---

## Architecture

```
┌──────────────────────────┐         ┌────────────────────────────────────────┐
│   Django Customer Portal │         │        Odoo 19 Enterprise              │
│   (loan_system/)         │         │        (odoo_addons/)                  │
│                          │         │                                        │
│  Customer registration   │◄──────►│  alba_loans    — Loan lifecycle        │
│  KYC & documents         │  REST  │  alba_investors — Investor accounts     │
│  Loan applications       │  API + │  alba_integration — API bridge         │
│  Application tracking    │ webhooks│  alba_sms      — Bulk SMS              │
│  Active loan dashboard   │         │                                        │
└──────────┬───────────────┘         └──────────────┬─────────────────────────┘
           │                                         │
           └──────────────────┬──────────────────────┘
                              │
                    ┌─────────▼────────┐
                    │   PostgreSQL     │
                    │   (shared DB)    │
                    └──────────────────┘
```

---

## Django Portal (`loan_system/`)

### Project Structure

```
loan_system/
├── config/              # Settings, urls, wsgi, asgi
├── core/                # Email-based auth, RBAC, audit log, dashboard routing,
│                        # document verification
├── loans/               # Customer models, loan application workflow,
│                        # repayment tracking
├── templates/
│   └── partials/
│       └── navbar.html  # Shared navbar
├── static/              # Compiled frontend assets
└── frontend/            # Vite + React/TypeScript source (document verification UI)
```

### URL Map

| URL | Description |
|---|---|
| `/` | Public landing page |
| `/login/` | Customer / admin login |
| `/register/` | New customer registration |
| `/dashboard/` | Role-based redirect |
| `/customer/dashboard/` | Customer overview |
| `/loans/` | Loan dashboard |
| `/loans/apply/` | New loan application |
| `/loans/applications/` | Application history |
| `/loans/my-loans/` | Active loans |
| `/loans/profile/` | KYC profile |
| `/api/calculate-loan/` | AJAX loan calculator |

---

## Odoo Addons (`odoo_addons/`)

### `alba_loans` — Core Loan Management

The central addon covering the full loan lifecycle from product configuration through to closure.

**Loan Products**
- Salary advance, business loan, asset financing
- Configurable interest methods: flat rate and reducing balance
- Amortisation schedule generation

**Application Workflow**
- 9-stage pipeline with Kanban view
- KYC customer profiles linked to applications
- Disbursement wizard with automated journal entries
- Repayment posting with principal / interest / fees split

**Portfolio Management**
- PAR bucket tracking (PAR 1–30, 31–60, 61–90)
- NPL flagging
- Daily and weekly scheduled crons

**M-Pesa Daraja Integration**
- STK Push (Lipa Na M-Pesa)
- C2B (customer-to-business payments)
- B2C (business-to-customer disbursements)

**Reporting**
- Loan statement PDF per borrower

**Security Groups:** Loan Officer · Loan Manager · Operations Manager · Finance · Director

---

### `alba_investors` — Investor Management

Manages investor capital accounts alongside the loan book.

- Investor profiles with KYC
- Investment accounts: fixed-term and open-ended
- Monthly compound interest accrual cron
- Interest payable journal entries posted automatically
- Monthly investor statement generation
- M-Pesa B2C payout to investors

---

### `alba_integration` — Django ↔ Odoo Bridge

Handles all communication between the Django portal and Odoo in both directions.

#### Direction: Django → Odoo (inbound REST)

| Method | Endpoint | Action |
|---|---|---|
| `POST` | `/alba/api/v1/customers` | Create or update a customer record |
| `POST` | `/alba/api/v1/applications` | Submit a loan application |
| `PATCH` | `/alba/api/v1/applications/<id>/status` | Change application state |
| `POST` | `/alba/api/v1/payments` | Record a repayment |

#### Direction: Odoo → Django (outbound HMAC-SHA256 webhooks)

| Event |
|---|
| `application.status_changed` |
| `loan.disbursed` |
| `loan.npl_flagged` |
| `loan.closed` |
| `loan.instalment_overdue` |
| `loan.maturing_soon` |
| `payment.matched` |
| `customer.kyc_verified` |
| `portfolio.stats_updated` |

#### Additional Features

- API key management
- Retry queue with exponential backoff: 2 min → 5 min → 15 min → 1 h → 4 h
- Webhook audit log
- Sync log with automated retention cron

**Security Groups:** Integration User (read webhook logs) · Integration Admin (manage API keys)

---

### `alba_sms` — Bulk SMS

Multi-provider SMS engine with templating, campaign management, and a full audit trail.

**Provider Adapters**
- Africa's Talking
- Twilio
- Vonage
- Generic HTTP (configurable)

**Template Engine**
- `{placeholder}` substitution syntax
- 8 default templates seeded on install

**Automated Hooks**
- Overdue payment reminders
- Maturity reminders
- Payment confirmation notifications
- Collection stage reminders
- Investor interest credited notifications

**Bulk Campaign Engine**

Audience targeting options:

| Audience |
|---|
| All customers |
| PAR 1–30 |
| PAR 31–60 |
| PAR 61–90 |
| NPL |
| Maturing loans |
| Investors |
| Custom domain filter |

**Delivery Receipts**
- DLR webhook endpoint: `/alba/sms/dlr`
- Full SMS audit log per message

**Kill Switch**

Set `alba_sms.enabled = 0` in **Odoo → Settings → Technical → System Parameters** to suspend all outbound SMS immediately without uninstalling the addon.

**Security Groups:** SMS User (read SMS logs) · SMS Officer (run campaigns) · SMS Admin (configure providers)

> ⚠️ **Dual-notification note:** `alba_sms` and `alba_integration` both hook into overdue, maturity, and payment events. Ensure the Django portal does **not** also SMS customers on those same webhook events to avoid duplicate notifications.

---

## Module Dependency Graph

```
alba_loans ◄── alba_investors
    ▲                ▲
    └────────────────┘
             ▲
      alba_integration
             ▲
          alba_sms
```

> `alba_sms` depends directly on `alba_loans` and `alba_investors`. It does **not** depend on `alba_integration`.

---

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key — no default, startup fails if missing |
| `DEBUG` | `True` for development, `False` for production |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hostnames |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL user |
| `DB_PASSWORD` | PostgreSQL password — no default, startup fails if missing |
| `DB_HOST` | Database host (default: `localhost`) |
| `DB_PORT` | Database port (default: `5432`) |
| `ODOO_URL` | Base URL of the Odoo instance |
| `ODOO_API_KEY` | API key for Django → Odoo REST calls |
| `ODOO_WEBHOOK_SECRET` | HMAC-SHA256 secret for verifying Odoo → Django webhooks |
| `SESSION_COOKIE_SECURE` | Set `True` in production |
| `CSRF_COOKIE_SECURE` | Set `True` in production |

---

## Quick Start (Django)

```bash
git clone <repo>
cd ACCT.f
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit **http://127.0.0.1:8000**

---

## User Roles

| Role | System | Access |
|---|---|---|
| `CUSTOMER` | Django portal | Apply for loans, track applications and repayments |
| `ADMIN` | Django admin | Manage users, approve registrations |
| Loan Officer | Odoo — `alba_loans` | Process and assess loan applications |
| Loan Manager | Odoo — `alba_loans` | Approve loans, manage officers |
| Finance | Odoo — `alba_loans` | Disbursement, repayment posting, accounting entries |
| Operations Manager | Odoo — `alba_loans` | Cross-functional operations oversight |
| Director | Odoo — `alba_loans` | Full read access, portfolio reporting |
| Investor | Odoo — `alba_investors` | View investment accounts and statements |
| Integration User | Odoo — `alba_integration` | Read webhook and sync logs |
| Integration Admin | Odoo — `alba_integration` | Manage API keys and retry queue |
| SMS User | Odoo — `alba_sms` | Read SMS logs |
| SMS Officer | Odoo — `alba_sms` | Run bulk campaigns |
| SMS Admin | Odoo — `alba_sms` | Configure providers and templates |

---

## Support

**Alba Capital** — internal system.
Contact the system administrator for access or issues.