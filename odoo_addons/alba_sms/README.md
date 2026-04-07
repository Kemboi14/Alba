# Alba Capital — Bulk SMS (`alba_sms`)

**Odoo 19 Enterprise · Version 19.0.1.0.0**

Outbound SMS notifications and bulk campaign engine for Alba Capital.
Hooks into `alba_loans` and `alba_investors` via `_inherit` — zero changes
to the core modules. Can be toggled on or off independently without
affecting any other addon.

---

## Table of Contents

1. [Overview](#overview)
2. [Module Structure](#module-structure)
3. [Models](#models)
4. [Automated Hooks](#automated-hooks)
5. [Bulk Campaigns](#bulk-campaigns)
6. [Provider Adapter](#provider-adapter)
7. [Template Engine](#template-engine)
8. [Delivery Receipts (DLR)](#delivery-receipts-dlr)
9. [Security Groups](#security-groups)
10. [Installation](#installation)
11. [Configuration](#configuration)
12. [Relationship with `alba_integration`](#relationship-with-alba_integration)
13. [Cron Jobs](#cron-jobs)
14. [Troubleshooting](#troubleshooting)
15. [Changelog](#changelog)

---

## Overview

`alba_sms` adds a fully configurable outbound SMS layer to the Alba Capital
Odoo back-office. It covers the entire customer and investor communication
lifecycle:

| Communication | Trigger |
|---|---|
| Loan overdue reminders | Daily cron — 1 / 3 / 7 / 14 / 30 day buckets |
| Loan maturity reminders | Weekly cron — loans maturing within 30 days |
| Payment confirmation | Every repayment posted (`action_post`) |
| Collection stage reminder | `action_send_collection_reminder()` — uses the `sms_template` field already on `alba.loan.collection.stage` |
| Investor interest credited | Every interest accrual posted (`action_post`) |
| Bulk campaigns | Manual or scheduled — any audience segment |

All automated hooks call `super()` first and wrap the SMS block in a
broad `try/except` so a gateway outage can never break the underlying
business logic.

---

## Module Structure

```
alba_sms/
├── __manifest__.py
├── __init__.py
│
├── models/
│   ├── __init__.py
│   ├── sms_provider.py       # alba.sms.provider — HTTP adapter
│   ├── sms_template.py       # alba.sms.template — {placeholder} engine
│   ├── sms_log.py            # alba.sms.log — audit trail
│   ├── sms_batch.py          # alba.sms.batch + alba.sms.batch.line
│   ├── loan_hooks.py         # _inherit alba.loan → overdue + maturity
│   ├── collection_hooks.py   # _inherit alba.loan → collection reminder
│   ├── repayment_hooks.py    # _inherit alba.loan.repayment → payment confirm
│   └── investor_hooks.py     # _inherit alba.interest.accrual → interest SMS
│
├── wizard/
│   ├── __init__.py
│   ├── bulk_sms_wizard.py    # alba.sms.wizard — ad-hoc sender from list views
│   └── bulk_sms_wizard_views.xml
│
├── controllers/
│   ├── __init__.py
│   └── dlr_controller.py     # POST /alba/sms/dlr — delivery receipts
│
├── security/
│   ├── security.xml          # 3 groups: user / officer / admin
│   └── ir.model.access.csv   # 18 ACL rows across 5 models
│
├── views/
│   ├── actions.xml
│   ├── sms_provider_views.xml
│   ├── sms_template_views.xml
│   ├── sms_log_views.xml
│   ├── sms_batch_views.xml
│   └── menus.xml
│
└── data/
    ├── sms_template_data.xml  # 8 default templates (noupdate=1)
    └── cron_data.xml          # 15-min batch cron + alba_sms.enabled param
```

---

## Models

### `alba.sms.provider` — Gateway Adapter

Stores all credentials and HTTP configuration for a single SMS gateway.
All sensitive fields (`api_key`, `api_secret`) are restricted to
`group_sms_admin` and never shown to lower-privilege users.

| Field | Type | Description |
|---|---|---|
| `name` | Char | Display name for this provider |
| `provider_type` | Selection | Africa's Talking / Twilio / Vonage / Generic HTTP |
| `api_url` | Char | Full API endpoint URL |
| `api_key` | Char | API key / Account SID (admin-only) |
| `api_secret` | Char | API secret / Auth Token (admin-only) |
| `username` | Char | Africa's Talking username |
| `sender_id` | Char | Short code or alphanumeric sender (e.g. `ALBA`) |
| `auth_type` | Selection | Header / Query Param / Basic Auth |
| `auth_header_name` | Char | Header name for API key (default: `apiKey`) |
| `phone_param_name` | Char | Payload field for phone (default: `to`) |
| `message_param_name` | Char | Payload field for message (default: `message`) |
| `extra_params` | Text | JSON blob — provider-specific extra fields |
| `is_active` | Boolean | Enables/disables this provider |
| `timeout_s` | Integer | HTTP request timeout in seconds (default: 30) |
| `log_count` | Integer | Count of `alba.sms.log` entries (computed) |

**Key method:** `send_sms(phone, message, res_model, res_id, template_id, batch_line_id)`

Returns `(success: bool, provider_msg_id: str, error_msg: str)`.
Normalises the Kenyan phone number (07xx → 254xx), builds the
provider-specific HTTP request, fires it, writes an `alba.sms.log`
entry regardless of outcome, and returns the result tuple.

---

### `alba.sms.template` — Message Templates

Reusable templates with simple `{placeholder}` substitution. Intentionally
not Jinja — safe for non-technical admins.

| Field | Type | Description |
|---|---|---|
| `name` | Char | Human-readable template name |
| `code` | Char | Stable machine key used in Python (unique) |
| `category` | Selection | Loan overdue / maturity / payment / disbursed / approved / rejected / collection / investor interest / bulk |
| `content` | Text | Message body with `{placeholder}` tokens |
| `is_active` | Boolean | Active flag |
| `char_count` | Integer | Character count (computed, store=False) |
| `preview` | Text | Rendered with dummy data (computed, store=False) |

**Available placeholders:**

| Placeholder | Value |
|---|---|
| `{customer_name}` | Borrower's full name |
| `{loan_number}` | Loan reference (e.g. `LN-0001`) |
| `{amount}` | Relevant monetary amount |
| `{due_date}` | Instalment or payment due date |
| `{days_overdue}` | Days past due |
| `{outstanding_balance}` | Total balance still owed |
| `{maturity_date}` | Loan end date |
| `{company_name}` | Sending company name |
| `{investor_name}` | Investor's full name |
| `{investment_number}` | Investment reference (e.g. `INV-0001`) |
| `{interest_amount}` | Interest amount credited or accrued |

**Key methods:**
- `render(context_dict)` — `str.format_map()`; returns raw content unchanged on `KeyError` (never raises)
- `get_by_code(code)` — `@api.model` lookup by code, returns record or `False`

---

### `alba.sms.log` — Audit Trail

Append-only log of every outbound SMS. Mirrors the structure and
conventions of `alba.webhook.log` in `alba_integration`.

| Field | Type | Description |
|---|---|---|
| `phone_number` | Char | Destination phone (normalised to 254XXXXXXXXX) |
| `message` | Text | Full SMS body sent |
| `status` | Selection | queued / sent / delivered / failed |
| `provider_id` | Many2one | Provider that sent this message |
| `template_id` | Many2one | Template used (if any) |
| `batch_id` | Many2one | Originating batch campaign (if any) |
| `batch_line_id` | Many2one | Originating batch line (if any) |
| `provider_msg_id` | Char | External message ID (for DLR correlation) |
| `error_message` | Text | Error detail when status is `failed` |
| `sent_at` | Datetime | Timestamp when gateway accepted the message |
| `res_model` | Char | Source Odoo model (e.g. `alba.loan`) |
| `res_id` | Integer | Source record ID |

**Key methods:**
- `mark_delivered(provider_msg_id=None)` — updates status to `delivered`
- `mark_failed(error)` — updates status to `failed` and stores error detail

---

### `alba.sms.batch` — Bulk Campaign

| Field | Type | Description |
|---|---|---|
| `name` | Char | Campaign name |
| `template_id` | Many2one | Message template |
| `provider_id` | Many2one | SMS provider |
| `state` | Selection | draft / scheduled / running / done / cancelled |
| `scheduled_at` | Datetime | Send time for scheduled campaigns |
| `target_type` | Selection | See target audience options below |
| `target_domain` | Text | JSON domain when `target_type = custom_domain` |
| `manual_phones` | Text | One phone per line when `target_type = manual_list` |
| `total_count` | Integer | Total lines generated (computed) |
| `sent_count` | Integer | Lines in sent/delivered state (computed) |
| `delivered_count` | Integer | Lines in delivered state (computed) |
| `failed_count` | Integer | Lines in failed state (computed) |
| `progress_pct` | Float | (sent + delivered + failed) / total × 100 (computed) |

**Target audience options:**

| Value | Description |
|---|---|
| `all_customers` | All active `alba.customer` records |
| `overdue_loans` | All loans with `days_in_arrears > 0` |
| `par_1_30` | Loans overdue 1–30 days |
| `par_31_60` | Loans overdue 31–60 days |
| `par_61_90` | Loans overdue 61–90 days |
| `npl_loans` | Loans in state `npl` |
| `maturing_soon` | Active loans maturing within 30 days |
| `all_investors` | All active `alba.investor` records |
| `custom_domain` | Any JSON Odoo domain evaluated against `alba.loan` or `alba.investor` |
| `manual_list` | Free-text phone list (one per line) |

**Phone resolution priority** (same in all hooks, batch, and wizard):
`mpesa_number` → `partner_id.mobile` → `partner_id.phone`

**Key actions:**
- `action_generate_lines()` — resolves audience, renders messages, creates batch lines
- `action_send_now()` — sets state to `running`, calls `_process_lines()`
- `action_schedule()` — sets state to `scheduled` (cron picks it up)
- `_process_lines(page_size=100)` — sends one page, marks batch `done` when empty
- `cron_process_scheduled_batches()` — `@api.model` cron entry point

---

### `alba.sms.batch.line`

One row per recipient within a batch. Created by `action_generate_lines()`.

| Field | Description |
|---|---|
| `phone_number` | Resolved phone number |
| `message` | Fully rendered message for this recipient |
| `status` | queued / sent / delivered / failed |
| `log_id` | Link to the `alba.sms.log` entry after sending |
| `error_message` | Gateway error if failed |

---

## Automated Hooks

All hooks follow the same pattern:
1. Call `super()` first — core logic always runs
2. Check `alba_sms.enabled` system parameter
3. Look up active provider and template
4. Resolve phone number
5. Render and send
6. Wrap everything in `try/except` — SMS failure cannot roll back business logic

### Hook: `alba.loan` — Overdue Alerts

**File:** `models/loan_hooks.py`

Overrides `cron_send_overdue_alerts()`. After the parent cron posts
chatter and fires integration webhooks, this hook queries the same
overdue repayment schedules (1 / 3 / 7 / 14 / 30 days) and sends an
SMS to each affected customer. Template code: `loan_overdue_reminder`.

### Hook: `alba.loan` — Maturity Reminders

**File:** `models/loan_hooks.py`

Overrides `cron_send_maturity_reminders()`. Sends SMS to customers
whose loans mature within 30 days. Template code: `maturity_reminder`.

### Hook: `alba.loan` — Collection Reminder

**File:** `models/collection_hooks.py`

Overrides `action_send_collection_reminder()`. This method already
existed in `alba_loans` and sent email only. The override reads the
`sms_template` field that was **already defined** on
`alba.loan.collection.stage` (with default content) but was never
called. Now it actually sends the SMS.

Substitution tokens in the collection stage `sms_template` field:
`{customer_name}`, `{loan_number}`, `{amount}`, `{days}`, `{company_name}`.

### Hook: `alba.loan.repayment` — Payment Confirmation

**File:** `models/repayment_hooks.py`

Overrides `action_post()`. After accounting journal entries are posted,
sends a payment confirmation SMS. Template code: `payment_confirmation`.

### Hook: `alba.interest.accrual` — Investor Interest

**File:** `models/investor_hooks.py`

Overrides `action_post()` on `alba.interest.accrual`. After the
journal entry is posted, sends an interest-credited SMS to the
investor. Template code: `investor_interest`.

---

## Bulk Campaigns

### Creating a Campaign

1. Go to **Alba SMS → Campaigns → New**
2. Select **Template** and **Provider**
3. Choose a **Target Type** and configure audience (domain or phone list)
4. Click **Generate Recipients** — system resolves phones and renders messages
5. Review the Recipients tab — edit individual lines if needed
6. Click **Send Now** (immediate) or set **Send At** and click **Schedule**

### Background Processing

The `cron_process_scheduled_batches` cron runs every 15 minutes and:
- Activates `scheduled` batches whose `scheduled_at` has passed
- Continues `running` batches that still have `queued` lines
- Marks batches `done` when all lines are in a terminal state

Messages are sent in pages of 100 to avoid gateway rate limits.

### Ad-Hoc Wizard

The `alba.sms.wizard` can be launched from any loan or investor list
view via a server action button. Staff select a template and provider,
click **Preview Recipients** to see rendered messages, then click
**Send SMS** to dispatch immediately.

---

## Provider Adapter

### Built-in Provider Types

#### Africa's Talking
```json
{
  "provider_type": "africa_talking",
  "api_url": "https://api.africastalking.com/version1/messaging",
  "username": "<your-AT-username>",
  "api_key": "<your-AT-api-key>",
  "sender_id": "<your-registered-shortcode>"
}
```

#### Twilio
```json
{
  "provider_type": "twilio",
  "api_url": "https://api.twilio.com/2010-04-01/Accounts/<AccountSID>/Messages.json",
  "api_key": "<AccountSID>",
  "api_secret": "<AuthToken>",
  "sender_id": "+254700000000"
}
```
Twilio uses HTTP Basic Auth (`api_key` as username, `api_secret` as password).

#### Vonage / Nexmo
```json
{
  "provider_type": "vonage",
  "api_url": "https://rest.nexmo.com/sms/json",
  "api_key": "<your-vonage-api-key>",
  "api_secret": "<your-vonage-api-secret>",
  "sender_id": "ALBA"
}
```

#### Generic HTTP
Configure any HTTP-based SMS gateway without code changes:

```
Provider Type:      Generic HTTP
Auth Type:          API Key in Header   (or Query Param / Basic Auth)
Auth Header Name:   Authorization       (or apiKey / x-api-key)
Phone Param Name:   recipient           (whatever your provider expects)
Message Param Name: text                (whatever your provider expects)
Extra Params (JSON): {"channel": "sms", "service_id": "12345"}
```

### Phone Number Normalisation

All phone numbers are normalised to `254XXXXXXXXX` format before sending:

| Input | Output |
|---|---|
| `0712345678` | `254712345678` |
| `+254712345678` | `254712345678` |
| `712345678` | `254712345678` |
| `254712345678` | `254712345678` (no-op) |

Invalid numbers (not 12 digits starting with 254) are logged as
`failed` in `alba.sms.log` and skipped — they never reach the gateway.

---

## Template Engine

Templates use Python's `str.format_map()` with the `{placeholder}`
syntax. This was chosen over Jinja2 because:

1. **Safe for admins** — no code injection risk
2. **Transparent** — what you see is what gets sent
3. **Forgiving** — unknown placeholders log a warning and return the
   raw content; the SMS is never silently dropped

Example template content:
```
Dear {customer_name}, your loan {loan_number} payment of KES {amount}
is {days_overdue} day(s) overdue. Outstanding: KES {outstanding_balance}.
Pay now to avoid penalties. - {company_name}
```

The **Live Preview** section on the template form renders the message
with dummy data so you can see exactly how it will look before saving.

---

## Delivery Receipts (DLR)

### Endpoint

```
POST /alba/sms/dlr
POST /alba/sms/dlr/<provider_name>
```

No authentication required — providers do not consistently support
HMAC signing for DLR callbacks. The endpoint only updates existing
`alba.sms.log` records; it cannot create new ones.

### Expected payload (JSON or form-encoded)

```json
{
  "messageId": "ATXid_...",
  "status":    "delivered"
}
```

Accepted status values that map to **delivered:**
`delivered`, `success`, `DeliveredToTerminal`, `DeliveredToNetwork`

Accepted status values that map to **failed:**
`failed`, `error`, `DeliveryFailed`

The endpoint always returns HTTP 200 with `{"ok": true}` — even on
error — so providers never enter a retry storm.

### Africa's Talking DLR URL

In your AT dashboard, set the Delivery Report URL to:
```
https://your-odoo-instance.com/alba/sms/dlr/africa_talking
```

---

## Security Groups

| Group | XML ID | Permissions |
|---|---|---|
| SMS User | `group_sms_user` | Read SMS logs, view batch results |
| SMS Officer | `group_sms_officer` | Create/run campaigns, send ad-hoc SMS. Implies SMS User. |
| SMS Admin | `group_sms_admin` | Configure providers, manage templates, view API credentials, delete logs. Implies SMS Officer. |

Group implication chain: **SMS Admin → SMS Officer → SMS User**

---

## Installation

### Prerequisites

- `alba_loans` and `alba_investors` must be installed first
- `requests` Python package (already a dependency of `alba_loans`)

### Install Order

```
alba_loans  ──►  alba_investors  ──►  alba_sms
```

`alba_integration` is **not** a dependency. Install `alba_sms` before
or after `alba_integration` — order does not matter.

### Steps

**Odoo.sh:** Push this directory to your linked repository. Odoo.sh
detects the new module and rebuilds automatically.

**Self-hosted VPS:**
```bash
cp -r alba_sms/ /opt/odoo/custom-addons/
sudo systemctl restart odoo
```
Then in Odoo: **Settings → Apps → Update App List → search `alba_sms` → Install**

---

## Configuration

### 1. Add an SMS Provider

**Alba SMS → Configuration → SMS Providers → New**

Fill in: Provider Type, API Endpoint URL, API Key, Sender ID.
Click **Test Connection** to validate credentials before going live.

### 2. Review Message Templates

**Alba SMS → Configuration → Message Templates**

Eight default templates are seeded at install (`noupdate=1` — user
edits are preserved on upgrade). Review and adjust wording to match
Alba Capital's communication style.

### 3. Configure Collection Stage SMS

**Alba Loans → Configuration → Collection Stages** — open each stage
and verify the **SMS Template** field contains the message you want
sent when that stage's reminder fires. Available tokens:
`{customer_name}`, `{loan_number}`, `{amount}`, `{days}`, `{company_name}`.

### 4. Assign User Groups

**Settings → Users** — assign staff to `SMS User`, `SMS Officer`, or
`SMS Admin` as appropriate.

### 5. Kill Switch

To suspend all outbound SMS instantly without uninstalling:

**Settings → Technical → Parameters → System Parameters**
→ find `alba_sms.enabled` → change value from `1` to `0`

Set back to `1` to re-enable.

---

## Relationship with `alba_integration`

`alba_sms` and `alba_integration` are **independent peer modules**.
Neither depends on the other.

They operate on the same Odoo trigger points but deliver to
completely different destinations:

| Trigger | `alba_integration` | `alba_sms` |
|---|---|---|
| `cron_send_overdue_alerts` | `loan.instalment_overdue` webhook → Django | Overdue reminder SMS → customer phone |
| `cron_send_maturity_reminders` | `loan.maturing_soon` webhook → Django | Maturity reminder SMS → customer phone |
| `action_post` on repayment | `payment.matched` webhook → Django | Payment confirmation SMS → customer phone |

### ⚠️ Dual-Notification Risk

If your Django portal also sends a customer-facing notification
(email or SMS) when it receives one of the above webhooks, the
customer will receive **duplicate messages**.

**Resolution:** Once `alba_sms` is live, disable the Django-side
customer notification for those specific webhook event types.
Alternatively, add a `"sms_sent_by_odoo": true` flag to the webhook
payload in `_fire_loan_status_webhooks()` and check for it in your
Django handler.

---

## Cron Jobs

| Cron | Frequency | Method |
|---|---|---|
| Process Scheduled SMS Batches | Every 15 min | `alba.sms.batch.cron_process_scheduled_batches()` |

Manage at: **Settings → Technical → Automation → Scheduled Actions**
→ search "Alba SMS".

The automated hooks (overdue, maturity, collection, payment, interest)
are driven by the **existing crons in `alba_loans` and `alba_investors`**
— no additional crons are needed for those.

---

## Troubleshooting

### SMS not sending at all

1. Check `alba_sms.enabled` = `1` in System Parameters
2. Verify at least one active provider exists (**Alba SMS → Configuration → SMS Providers**)
3. Check **Alba SMS → SMS Logs → Failed** for error messages
4. Open the provider and click **Test Connection**

### Template renders with raw `{placeholder}` text

The placeholder name does not exist in the context dict for that
event. Open the template and check the available placeholders listed
in the **Message Content** field help text. Make sure you are using
the exact token names (case-sensitive).

### Batch stuck in `running` state

The 15-minute cron will resume it on the next run. To resume
immediately: open the batch → the cron will pick it up. If lines keep
failing, check the **Error** column in the Recipients tab.

### DLR not updating log status

1. Confirm the DLR URL is correctly set in your provider's dashboard
2. Check that Odoo's public URL is reachable from the internet
3. Verify the `provider_msg_id` in the DLR payload matches the value
   stored in **Alba SMS → SMS Logs** (the `Provider Message ID` field)

### Customers report receiving duplicate SMS

Both `alba_sms` and your Django portal are sending notifications.
See [Relationship with `alba_integration`](#relationship-with-alba_integration)
above for the resolution steps.

---

## Changelog

### 19.0.1.0.0 (initial release)

- `alba.sms.provider` — multi-provider HTTP adapter (Africa's Talking,
  Twilio, Vonage, Generic HTTP) with UI-only configuration
- `alba.sms.template` — `{placeholder}` template engine with 8 default
  templates seeded at install
- `alba.sms.log` — append-only SMS audit trail mirroring `alba.webhook.log`
- `alba.sms.batch` + `alba.sms.batch.line` — bulk campaign engine with
  10 audience targeting modes, immediate and scheduled dispatch
- `alba.sms.wizard` + `alba.sms.wizard.line` — ad-hoc multi-recipient
  sender dialog for loan and investor list views
- Automated hooks via `_inherit` (zero core module changes):
  `cron_send_overdue_alerts`, `cron_send_maturity_reminders`,
  `action_send_collection_reminder`, `alba.loan.repayment.action_post`,
  `alba.interest.accrual.action_post`
- DLR webhook controller at `/alba/sms/dlr[/<provider_name>]`
- Kill switch: `alba_sms.enabled` system parameter
- Security groups: SMS User, SMS Officer, SMS Admin (implied chain)
- Cron: Process Scheduled SMS Batches (every 15 minutes)
- Kenyan phone normalisation (07xx / 254xx / +254xx → 254XXXXXXXXX)
- Odoo 19 Enterprise compliant XML:
  - `<list>` (not `<tree>`), `<t t-name="card">` kanban templates
  - Direct `invisible=` expressions (no deprecated `attrs=`)
  - Cron records without `numbercall` / `doall` / `nextcall` fields