# Alba Capital — Odoo 19 Setup Guide

**Odoo 19 Community Edition with Python 3.12 on Arch Linux**  
Generated: 2026-06-08

---

## ✅ Installation Summary

Your Odoo 19 environment has been successfully created:

- **Odoo Version:** 19.0 Community Edition
- **Python Version:** 3.12.13
- **Virtual Environment:** `/home/nick/Alba/odoo_venv`
- **Odoo Source:** `/home/nick/Alba/odoo19`
- **Database:** PostgreSQL (alba_staging)
- **Configuration:** `/home/nick/Alba/odoo-local.conf`

---

## 🗂️ Directory Structure

```
Alba/
├── odoo_venv/                    # Python 3.12 virtual environment for Odoo
├── odoo19/                       # Odoo 19 Community Edition source
│   ├── odoo-bin                 # Odoo binary executable
│   ├── addons/                  # Standard Odoo modules
│   └── requirements.txt         # All Odoo dependencies
├── odoo_addons/                 # Alba Capital custom Odoo modules
│   ├── alba_loans/
│   ├── alba_investors/
│   ├── alba_integration/        # Django↔Odoo REST API bridge
│   └── alba_sms/
├── odoo-local.conf              # Odoo configuration (development)
├── setup-odoo.sh                # Odoo setup automation script
├── start_odoo.sh                # Standalone Odoo startup script
└── start_all.sh                 # Start Django + Odoo together
```

---

## 📋 Pre-requisites

### 1. PostgreSQL Installation

Odoo requires PostgreSQL database server:

```bash
# Install PostgreSQL and client libraries
sudo pacman -S postgresql postgresql-libs

# Initialize database cluster (if not already done)
sudo -u postgres initdb -D /var/lib/postgres/data

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify PostgreSQL is running
psql -U postgres -h localhost -c "SELECT version();"
```

### 2. Create Odoo Database User

```bash
# Create a PostgreSQL user 'nick' with database creation privileges
sudo -u postgres createuser -d nick

# Set password (optional)
sudo -u postgres psql -c "ALTER USER nick PASSWORD 'your_password';"
```

---

## 🚀 Running Odoo

### Option A: Automated Setup (Recommended)

```bash
cd /home/nick/Alba
./setup-odoo.sh
```

This script will:
- ✓ Verify the Python 3.12 virtual environment
- ✓ Verify Odoo 19 installation
- ✓ Check PostgreSQL connectivity
- ✓ Create the `alba_staging` database (if needed)
- ✓ Validate the configuration file

### Option B: Manual Startup

```bash
# 1. Activate the virtual environment
source /home/nick/Alba/odoo_venv/bin/activate

# 2. Start Odoo
cd /home/nick/Alba
./odoo19/odoo-bin --config=./odoo-local.conf -d alba_staging
```

### Option C: Using Startup Scripts

**Standalone Odoo:**
```bash
./start_odoo.sh
```

**Odoo + Django Together:**
```bash
./start_all.sh
```

---

## 🌐 Accessing Odoo

Once started, Odoo is available at:

**URL:** http://localhost:8069  
**Username:** admin  
**Password:** admin

### First Login

1. Navigate to http://localhost:8069
2. Enter credentials above
3. You'll be prompted to select/create a database
4. Database name: `alba_staging`
5. Administrator password: `admin`

---

## ⚙️ Configuration Reference

### Main Configuration File: `odoo-local.conf`

Key settings:

```ini
[options]
# Addon paths (standard + custom modules)
addons_path = /home/nick/Alba/odoo_addons,/home/nick/Alba/odoo19/addons

# Admin password for database management
admin_passwd = admin

# Database connection
db_host = localhost
db_port = 5432
db_user = nick
db_name = alba_staging

# Server settings
http_port = 8069
http_interface = 0.0.0.0

# Python interpreter (uses venv)
python_interpreter = /home/nick/Alba/odoo_venv/bin/python
```

### Database Configuration

- **Host:** localhost
- **Port:** 5432
- **Database:** alba_staging
- **User:** nick
- **Connection Method:** PostgreSQL native

---

## 🧩 Alba Custom Modules

Four custom Odoo addons power Alba Capital's back-office:

| Module | Sequence | Purpose | Status |
|--------|----------|---------|--------|
| `alba_loans` | 10 | Core loan lifecycle management | Installed in `odoo_addons/` |
| `alba_investors` | 20 | Investor accounts & interest calculations | Installed in `odoo_addons/` |
| `alba_integration` | 30 | REST API bridge to Django portal | Installed in `odoo_addons/` |
| `alba_sms` | 40 | Bulk SMS & automated notifications | Installed in `odoo_addons/` |

**To install these modules:**

1. Start Odoo
2. Go to Apps → Search → "Alba"
3. Click on each Alba module and click "Install"

Or via command line:

```bash
# Install all custom addons
./odoo19/odoo-bin --config=./odoo-local.conf -d alba_staging -i alba_loans,alba_investors,alba_integration,alba_sms
```

---

## 📊 Database Management

### Create Odoo Database

```bash
# Method 1: Automatic (first login via web UI)
# Navigate to http://localhost:8069, login with admin/admin

# Method 2: Command line
source /home/nick/Alba/odoo_venv/bin/activate
./odoo19/odoo-bin --config=./odoo-local.conf -d alba_staging
```

### PostgreSQL Direct Access

```bash
# Connect to Odoo database
psql -U nick -h localhost alba_staging

# View all Odoo tables
\dt

# Backup database
pg_dump -U nick alba_staging > alba_staging_backup.sql

# Restore database
psql -U nick alba_staging < alba_staging_backup.sql
```

---

## 🔍 Troubleshooting

### PostgreSQL Connection Error

```
Error: could not connect to server: Connection refused
```

**Solution:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Start it if not running
sudo systemctl start postgresql

# Verify user exists
sudo -u postgres psql -c "\du" | grep nick
```

### Odoo Module Import Errors

```
ModuleNotFoundError: No module named 'xyz'
```

**Solution:**
```bash
# Verify custom addons path in odoo-local.conf
grep "addons_path" /home/nick/Alba/odoo-local.conf

# Ensure modules are in /home/nick/Alba/odoo_addons/
ls -la /home/nick/Alba/odoo_addons/
```

### Odoo Won't Start

**Check logs:**
```bash
tail -f /tmp/odoo19.log
```

**Common causes:**
1. PostgreSQL not running → `sudo systemctl start postgresql`
2. Port 8069 in use → `sudo lsof -i :8069` then kill process
3. Python dependencies missing → `pip install -r requirements.txt`

### Database Already Exists

If you get "database already exists" error when initializing:

```bash
# Option 1: Use existing database
./odoo19/odoo-bin --config=./odoo-local.conf -d alba_staging

# Option 2: Drop and recreate
dropdb -U nick alba_staging
createdb -U nick alba_staging
```

---

## 📈 Performance Tuning

### For Development

Default settings in `odoo-local.conf` are optimized for development:

```ini
# Keep debug logging
log_level = debug

# Single worker (slower but easier debugging)
workers = 0
```

### For Production

Adjust for better performance:

```ini
# Reduce logging verbosity
log_level = info

# Enable multi-worker mode
workers = 4
max_cron_threads = 2

# Memory limits
limit_memory_soft = 2147483648  # 2GB
limit_memory_hard = 2684354560  # 2.5GB
```

---

## 🔗 Integrating Django ↔ Odoo

The `alba_integration` module provides REST API endpoints for Django to communicate with Odoo:

### Webhook Configuration

In Django `.env`:
```env
WEBHOOK_URL=http://localhost:8069/webhooks/
```

### API Endpoints (Odoo)

Available endpoints in `alba_integration`:
- `POST /api/loans/` - Create loan in Odoo
- `POST /api/investors/` - Create investor account
- `POST /api/sync/` - Sync data between systems

### Testing Integration

```bash
# From Django environment
curl -X POST http://localhost:8069/api/loans/ \
  -H "Content-Type: application/json" \
  -d '{"customer_id": 123, "amount": 5000}'
```

---

## 📝 Useful Commands

| Command | Purpose |
|---------|---------|
| `source odoo_venv/bin/activate` | Activate Odoo Python environment |
| `./odoo19/odoo-bin --version` | Check Odoo version |
| `./odoo19/odoo-bin --help` | View all Odoo options |
| `deactivate` | Exit Python environment |
| `pip list` | List all Python packages |
| `psql -U nick alba_staging` | Connect to Odoo database |

---

## 🚀 Starting Both Systems

To run Django (port 8000) + Odoo (port 8069) together:

**Terminal 1 - Odoo:**
```bash
cd /home/nick/Alba
./start_odoo.sh
```

**Terminal 2 - Django:**
```bash
source venv/bin/activate
python manage.py runserver
```

**Terminal 3 - React Frontend:**
```bash
cd frontend
npm run dev
```

---

## 📚 Additional Resources

- [Odoo 19 Documentation](https://www.odoo.com/documentation/19.0)
- [Odoo Developer Guide](https://www.odoo.com/documentation/19.0/developer)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

**Setup complete! 🎉**

Your Odoo 19 environment is ready to use. Start with `./setup-odoo.sh` or `./start_odoo.sh` to begin.
