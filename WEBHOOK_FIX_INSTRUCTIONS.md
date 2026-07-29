# Webhook Authentication Fix Instructions

## Problem
Odoo webhooks to Django are failing with 401 Unauthorized errors because the webhook secret is not properly configured in the Django admin portal.

## Solution
Configure the webhook secret in the Django admin portal (OdooConfig) to match the secret that Odoo is using to sign webhooks.

## Steps to Fix:

### 1. Get the Webhook Secret from Odoo
1. Log in to your Odoo instance (https://erp.albacapital.co.ke)
2. Navigate to: **Alba Integration → API Keys**
3. Find the active API key record being used for this integration
4. Copy the **Webhook Secret** value (it should be a 64-character hex string)

### 2. Configure Webhook Secret in Django Admin Portal
1. Log in to your Django admin portal (https://portal.albacapital.co.ke/admin/)
2. Navigate to: **Core → Odoo Configs**
3. Find the active Odoo configuration record
4. Edit the record and paste the webhook secret in the **Webhook Secret** field
5. Save the configuration

### 3. Verify Other Odoo Integration Settings
In the same Odoo Config record, ensure these are also configured:
- **Odoo URL**: https://erp.albacapital.co.ke
- **API Key**: The API key from Odoo (should already be configured)
- **Database**: alba_staging (or your Odoo database name)
- **Outbound Webhook URL**: https://portal.albacapital.co.ke/api/v1/webhooks/odoo/
- **Active**: Should be checked/enabled

### 4. Test Webhook Configuration
1. Trigger a health check from Odoo
2. Check Django logs for successful webhook deliveries
3. Verify the webhook is using the admin-configured secret
4. Look for log message: "Using webhook secret from admin configuration"

## Important Notes:
- The webhook secret in Odoo and Django admin portal must match exactly
- Any whitespace difference will cause HMAC verification to fail
- The webhook receiver now checks admin configuration first, then falls back to environment variable
- This fix is in the Django portal only - no changes to Odoo addon module needed

## After the Fix:
Once configured correctly, webhooks should work properly:
- `integration.health_check` - Should return 200 OK
- `portfolio.stats_updated` - Should return 200 OK  
- `loan.classification_updated` - Should return 200 OK
- All other webhook events should work normally

The webhook authentication failures will be resolved and the Django portal will receive updates from Odoo properly.