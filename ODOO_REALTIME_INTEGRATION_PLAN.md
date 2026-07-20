# Odoo ↔ Django real-time integration plan

## Current state reviewed

I reviewed the existing integration path across the Django portal, the Odoo bridge addon, and the Alba loan addon:

- Django outbound sync client: [core/services/odoo_sync.py](core/services/odoo_sync.py)
- Django inbound webhook receiver: [core/services/webhooks.py](core/services/webhooks.py)
- Odoo REST API endpoints: [odoo_addons/alba_integration/controllers/api_controller.py](odoo_addons/alba_integration/controllers/api_controller.py)
- Odoo loan application model: [odoo_addons/alba_loans/models/loan_application.py](odoo_addons/alba_loans/models/loan_application.py)
- Portal submission flow: [loans/views.py](loans/views.py)

## What is already working

- The portal can submit applications to Odoo through the REST API.
- The Odoo integration addon already exposes endpoints for customers, applications, status updates, and payments.
- The Django side already has webhook reception, idempotency handling, and retry logic.
- The portal already stores Odoo IDs and sync states on Django models.

## Main gaps to close

1. Real-time visibility
   - The portal should immediately show whether an object is pending, syncing, synced, or failed.
   - The UI should surface the latest Odoo state and last sync timestamp without waiting for manual refresh.

2. Full audit trail
   - Every outbound post and inbound webhook should be logged with payload, result, timestamp, and status.
   - These logs should be accessible from both the Django admin and the Odoo-side integration screens.

3. Reliable state alignment
   - Django should mirror the Odoo workflow states for applications and loans.
   - Webhooks should be the authoritative source for downstream updates such as approval, disbursal, repayment posting, and status changes.

4. Robust real-time posting
   - Application submission and payment posting should be synchronous for the user-facing flow.
   - Status updates and secondary syncing should use a background worker or retry queue so they do not block the customer experience.

## Implementation plan

### Phase 1 — harden the sync contract
- Confirm the exact payloads expected by Odoo for:
  - customer creation / KYC updates
  - application creation
  - application status transitions
  - repayment posting
- Validate that Django sends the same field names and values expected by the Alba loan addon.
- Add a shared payload validation layer before requests go out.

### Phase 2 — make sync state observable
- Add a consistent sync lifecycle on Django models:
  - pending
  - syncing
  - success
  - failed
- Persist the last request/response summary, error cause, and Odoo record identifier.
- Expose these values in the application and loan detail UI.

### Phase 3 — add complete logging
- Record every outbound API call in Django with:
  - endpoint
  - request payload
  - response status
  - response body
  - timestamp
  - object IDs
- Record every inbound Odoo webhook with:
  - event type
  - delivery ID
  - raw payload
  - processing result
  - timestamps
- Make these logs visible from the admin and/or dedicated views.

### Phase 4 — enable near real-time state sync
- Keep the initial application submission and payment posting synchronous.
- Use webhook-driven updates from Odoo for status changes and loan lifecycle changes.
- Add a retry queue for transient failures so the portal can recover automatically.
- When a webhook arrives, update the Django record immediately and refresh the UI state.

### Phase 5 — verify end-to-end
- Test the happy path:
  - create customer in Django → Odoo receives it
  - submit application → Odoo creates it and returns an Odoo ID
  - update application state → Odoo updates it and sends webhook back
  - post payment → Odoo creates repayment and sends webhook back
- Verify the portal reflects the updated state without manual reload.

## Files to update

- [core/services/odoo_sync.py](core/services/odoo_sync.py)
- [core/services/webhooks.py](core/services/webhooks.py)
- [loans/views.py](loans/views.py)
- [loans/models.py](loans/models.py)
- [templates/loans/application_detail.html](templates/loans/application_detail.html)
- [templates/loans/loan_detail.html](templates/loans/loan_detail.html)
- [odoo_addons/alba_integration/controllers/api_controller.py](odoo_addons/alba_integration/controllers/api_controller.py)

## Acceptance criteria

- A submitted application is posted to Odoo and immediately shows the Odoo application ID.
- Status changes made in Odoo update the Django portal in near real time.
- Every sync attempt produces a visible log entry.
- Failed syncs are retried automatically and surfaced clearly to the user.
- Django and Odoo loan/application status labels remain aligned.
