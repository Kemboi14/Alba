# Webhook Authentication Fix Instructions

## Problem
Odoo webhooks to Django are failing with 401 Unauthorized errors because the `ODOO_WEBHOOK_SECRET` is not configured in the Django `.env` file.

## Solution
You need to configure the webhook secret from Odoo in your Django `.env` file.

## Steps to Fix:

### 1. Get the Webhook Secret from Odoo
1. Log in to your Odoo instance (https://erp.albacapital.co.ke)
2. Navigate to: **Alba Integration → API Keys**
3. Find the active API key record being used for this integration
4. Copy the **Webhook Secret** value (it should be a 64-character hex string)

### 2. Update Django .env File
1. Edit `/opt/odoo/Alba/.env` (or the path to your production .env file)
2. Find the `ODOO_WEBHOOK_SECRET=` line
3. Paste the webhook secret after the equals sign
4. It should look like: `ODOO_WEBHOOK_SECRET=your_64_char_hex_secret_here`

### 3. Get the API Key from Odoo (if not already configured)
1. In the same API key record in Odoo, copy the **Key** value
2. Update the `ODOO_API_KEY=` line in your Django .env file
3. It should look like: `ODOO_API_KEY=your_api_key_here`

### 4. Restart Django Application
After updating the .env file, restart your Django application for the changes to take effect:

```bash
# If using gunicorn
sudo systemctl restart alba-loans

# Or if using manual start
pkill -f gunicorn
cd /opt/odoo/Alba
gunicorn config.wsgi:application --bind unix:/run/alba-loans/alba-loans.sock
```

### 5. Verify Webhook Configuration
1. Check that the webhook URL in Odoo API key record matches: `https://portal.albacapital.co.ke/api/v1/webhooks/odoo/`
2. Test the webhook by triggering a health check from Odoo
3. Check Django logs for successful webhook deliveries

## Important Notes:
- The webhook secret in Odoo and `ODOO_WEBHOOK_SECRET` in Django must match exactly
- Any whitespace difference will cause HMAC verification to fail
- The API key in Odoo and `ODOO_API_KEY` in Django must match exactly
- This fix is in the Django portal only - no changes to Odoo addon module needed

## After the Fix:
Once configured correctly, webhooks should work properly:
- `integration.health_check` - Should return 200 OK
- `portfolio.stats_updated` - Should return 200 OK  
- `loan.classification_updated` - Should return 200 OK
- All other webhook events should work normally

The webhook authentication failures will be resolved and the Django portal will receive updates from Odoo properly.