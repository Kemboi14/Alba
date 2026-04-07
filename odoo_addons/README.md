# Alba Capital — Odoo 19 Custom Addons

Four custom Odoo 19 Enterprise modules that power Alba Capital's back-office lending operations, investor management, Django portal integration, and outbound SMS communications.

---

## Module Overview

| Module | Sequence | Description | Depends on |
|---|---|---|---|
| `alba_loans` | 10 | Core loan lifecycle | base, account, mail, contacts |
| `alba_investors` | 20 | Investor accounts & interest | alba_loans |
| `alba_integration` | 30 | Django ↔ Odoo REST bridge | alba_loans, alba_investors |
| `alba_sms` | 40 | Bulk SMS & automated notifications | alba_loans, alba_investors |

### Dependency Chain

```
[base] [account] [mail] [contacts]
          ↓
      alba_loans
          ↓
    alba_investors
          ↓
  alba_integration    alba_sms
  (Django bridge)  (SMS layer)
```

> `alba_integration` and `alba_sms` are both peers — neither depends on the other.

---

## 1. `alba_loans` — Core Loan Management

**Models:**
`alba.loan`, `alba.loan.application`, `alba.customer`, `alba.loan.product`, `alba.loan.repayment`, `alba.repayment.schedule`, `alba.mpesa.config`, `alba.mpesa.transaction`, `alba.loan.collection.stage`, `alba.loan.collection.log`

**Key Features:**

- 9-stage application workflow: Draft → Submitted → Under Review → Credit Analysis → Pending Approval → Approved → Employer Verification → Guarantor Confirmation → Disbursed, plus Rejected/Cancelled terminals
- Flat rate and reducing balance amortisation schedule generation
- Disbursement wizard with automatic journal entries (DR Loan Receivable / CR Bank)
- Repayment posting with principal/interest/fees/penalty split
- PAR bucket tracking (1–30, 31–60, 61–90, 91–180, 180+ days)
- NPL auto-flagging at 90 days overdue (daily cron)
- Collections escalation: Reminder → Collections → Recovery → Legal stages, each with configurable SMS template and activity type
- M-Pesa Daraja API: STK Push, C2B paybill/till callbacks, B2C payouts, OAuth2 token management
- Loan statement QWeb PDF report
- Daily/weekly/hourly crons (PAR update, overdue alerts, maturity reminders, M-Pesa reconciliation, portfolio stats push)

**Security Groups:** Loan Officer, Loan Manager, Operations Manager, Finance Officer, Director

---

## 2. `alba_investors` — Investor Management

**Models:**
`alba.investor`, `alba.investment`, `alba.investment.statement`, `alba.interest.accrual`, `alba.mpesa.transaction.investor`

**Key Features:**

- Investor profiles linked to `res.partner` with KYC workflow (pending → partial → complete → verified → rejected)
- Fixed-term and open-ended investment accounts
- Monthly compound interest accrual cron with journal entries (DR Interest Expense / CR Interest Payable)
- Monthly statement auto-generation wizard (emailed to investor)
- M-Pesa B2C integration for interest payouts
- Portfolio value tracking (principal + accrued interest per investor)

---

## 3. `alba_integration` — Django Portal Bridge

### Direction 1: Django → Odoo (Inbound REST API)

All endpoints under `/alba/api/v1/`, authenticated via `X-Alba-API-Key` header:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/loan-products` | List active products |
| `POST` | `/customers` | Create/update customer |
| `POST` | `/customers/<id>/kyc` | Update KYC status |
| `POST` | `/applications` | Submit loan application |
| `PATCH` | `/applications/<id>/status` | Transition state |
| `POST` | `/payments` | Record repayment |

### Direction 2: Odoo → Django (Outbound HMAC-SHA256 Webhooks)

Signed with `X-Alba-Signature: sha256=<hex>`:

| Event | Trigger |
|---|---|
| `application.status_changed` | Any application state transition |
| `loan.disbursed` | Loan moved to active |
| `loan.npl_flagged` | Loan flagged as non-performing |
| `loan.closed` | Loan fully repaid and closed |
| `loan.instalment_overdue` | Daily cron — instalment past due |
| `loan.maturing_soon` | Weekly cron — maturing within 30 days |
| `payment.matched` | Repayment posted and allocated |
| `payment.mpesa_received` | Inbound M-Pesa payment received |
| `customer.kyc_verified` | KYC verified in Odoo |
| `portfolio.stats_updated` | 6-hourly aggregate stats push |

### Infrastructure

- Retry queue with exponential backoff: 2m → 5m → 15m → 1h → 4h (max 5 attempts)
- Dead-letter alert webhook on final failure
- Sync audit log with 90-day retention
- IP allowlist per API key

---

## 4. `alba_sms` — Bulk SMS

**Models:**
`alba.sms.provider`, `alba.sms.template`, `alba.sms.log`, `alba.sms.batch`, `alba.sms.batch.line`, `alba.sms.wizard`, `alba.sms.wizard.line`

### Provider Support

| Provider | Notes |
|---|---|
| Africa's Talking | Kenya's primary SMS gateway |
| Twilio | Global |
| Vonage / Nexmo | Global |
| Generic HTTP | Configure any HTTP SMS gateway from the UI with no code changes (auth method, param names, extra JSON fields) |

### Template Engine

Simple `{placeholder}` substitution — not Jinja, safe for non-technical admins.

**Available placeholders:**
`{customer_name}`, `{loan_number}`, `{amount}`, `{due_date}`, `{days_overdue}`, `{outstanding_balance}`, `{maturity_date}`, `{company_name}`, `{investor_name}`, `{investment_number}`, `{interest_amount}`

### Default Templates Seeded at Install (8 total)

1. Loan Overdue Reminder
2. Loan Maturity Reminder
3. Payment Confirmation
4. Loan Disbursed
5. Application Approved
6. Application Rejected
7. Collection Stage Reminder
8. Investor Interest Credited

### Automated Hooks

Zero changes to core modules — all via `_inherit`:

| Hook | Event |
|---|---|
| `alba.loan` → `cron_send_overdue_alerts` | SMS per overdue customer (1/3/7/14/30 day buckets) |
| `alba.loan` → `cron_send_maturity_reminders` | SMS per maturing loan |
| `alba.loan` → `action_send_collection_reminder` | Uses the existing `sms_template` field on collection stages |
| `alba.loan.repayment` → `action_post` | Payment confirmation SMS |
| `alba.interest.accrual` → `action_post` | Investor interest credited SMS |

### Bulk Campaigns

Target by audience: all customers, PAR buckets, NPL, maturing, investors, custom domain filter, or manual list. Generate lines → preview → send now or schedule. Background cron processes in pages of 100.

### Delivery Receipts

Provider posts to `/alba/sms/dlr` or `/alba/sms/dlr/<provider_name>`. Updates `alba.sms.log` status to `delivered`.

### Kill Switch

Set system parameter `alba_sms.enabled` to `0` to suspend all SMS instantly without uninstalling the module.

### ⚠️ Relationship with `alba_integration`

Both modules hook into the same cron events. They are independent — `alba_sms` does **not** depend on `alba_integration` and vice versa. However, if Django also sends SMS on webhook events (e.g. `loan.instalment_overdue`), customers will receive duplicate messages. Coordinate with your Django webhook handler.

**Security Groups:** SMS User (read-only), SMS Officer (create/run campaigns), SMS Admin (configure providers, manage templates)

---

## Quick Install Reference

```bash
# Odoo.sh: add odoo_addons/ as custom addons path, push to repo

# Self-hosted:
cp -r odoo_addons/* /opt/odoo/custom-addons/
sudo systemctl restart odoo
# Then in Odoo: Apps → Update App List → install in order
```

**Install order:** `alba_loans` → `alba_investors` → `alba_integration` → `alba_sms`

---

## Development — Validate Locally

```bash
cd odoo_addons
python3 -m py_compile alba_loans/models/*.py alba_investors/models/*.py
python3 -m py_compile alba_integration/models/*.py alba_integration/controllers/*.py
python3 -m py_compile alba_sms/models/*.py alba_sms/controllers/*.py alba_sms/wizard/*.py
```

---

*Alba Capital ERP — Confidential*