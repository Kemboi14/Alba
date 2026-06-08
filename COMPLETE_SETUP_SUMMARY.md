# Alba Capital — Complete Environment Setup Summary

**Arch Linux with Python 3.12 (Django + Odoo 19)**  
Setup Date: 2026-06-08

---

## ✅ Installation Complete

Both the Django and Odoo 19 environments have been successfully configured with Python 3.12.

---

## 📦 Installed Components

### Python Environments

| Component | Location | Python | Status |
|-----------|----------|--------|--------|
| **Django Backend** | `/home/nick/Alba/venv` | 3.12.13 | ✅ Ready |
| **Odoo 19** | `/home/nick/Alba/odoo_venv` | 3.12.13 | ✅ Ready |

### Backend Frameworks

| Framework | Version | Port | Status |
|-----------|---------|------|--------|
| **Django** | 5.2.12 | 8000 | ✅ Installed |
| **Odoo** | 19.0 (Community) | 8069 | ✅ Installed |
| **Node.js** | 26.2.0 | 5173 | ✅ Installed |
| **React** | 18.2.0 | 5173 | ✅ Installed |

### Database

| Database | Version | Host | Port | Status |
|----------|---------|------|------|--------|
| **PostgreSQL** | Required | localhost | 5432 | ⚠️ Install Required |

---

## 📁 Project Structure

```
Alba/
├── venv/                        # Django Python 3.12 environment
├── odoo_venv/                   # Odoo Python 3.12 environment
├── odoo19/                      # Odoo 19 source code (47,679 files, 201 MB)
├── odoo_addons/                 # Alba custom Odoo modules
│   ├── alba_loans/             # Loan lifecycle
│   ├── alba_investors/         # Investor management
│   ├── alba_integration/       # Django↔Odoo API bridge
│   └── alba_sms/               # SMS communications
├── frontend/                    # React + Vite frontend
├── core/                        # Django core app
├── loans/                       # Django loans app
├── config/                      # Django configuration
├── templates/                   # HTML templates
├── static/                      # Static assets
├── .env                         # Django configuration (created)
├── odoo-local.conf              # Odoo configuration (updated)
├── setup-arch-linux.sh          # Django setup automation
├── setup-odoo.sh                # Odoo setup automation
├── start_odoo.sh                # Odoo startup script
├── start_all.sh                 # Start both systems
├── SETUP_ARCH_LINUX.md          # Django setup guide
└── SETUP_ODOO.md                # Odoo setup guide
```

---

## 🎯 Quick Start Guide

### Step 1: Install PostgreSQL (Required)

```bash
# Install PostgreSQL
sudo pacman -S postgresql postgresql-libs

# Initialize database
sudo -u postgres initdb -D /var/lib/postgres/data

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create user (if needed)
sudo -u postgres createuser -d nick
```

### Step 2: Run Setup Scripts

**Option A - Set Up Both Systems:**
```bash
cd /home/nick/Alba

# Setup Django
./setup-arch-linux.sh

# Setup Odoo (in new terminal)
./setup-odoo.sh
```

**Option B - Manual Setup:**
```bash
# Django migrations
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput

# Odoo initialization (will create database on first run)
source odoo_venv/bin/activate
./odoo19/odoo-bin --config=./odoo-local.conf -d alba_staging
```

### Step 3: Start Development Servers

**Terminal 1 - Odoo (http://localhost:8069):**
```bash
cd /home/nick/Alba
./start_odoo.sh
# Login: admin / admin
```

**Terminal 2 - Django (http://localhost:8000):**
```bash
cd /home/nick/Alba
source venv/bin/activate
python manage.py runserver
```

**Terminal 3 - React Frontend (http://localhost:5173):**
```bash
cd /home/nick/Alba/frontend
npm run dev
```

---

## 🌐 System Access Points

Once all servers are running:

| System | URL | Purpose |
|--------|-----|---------|
| **Odoo** | http://localhost:8069 | Back-office loan management |
| **Django API** | http://localhost:8000 | Backend REST API |
| **Django Admin** | http://localhost:8000/admin/ | Admin interface |
| **React Frontend** | http://localhost:5173 | Customer portal |

---

## 📊 Database Configuration

Both systems use the same PostgreSQL database server:

```
Host:     localhost
Port:     5432
```

**Django Database:**
- Name: `alba_capital`
- User: `postgres` (or configured in .env)

**Odoo Database:**
- Name: `alba_staging`
- User: `nick`

---

## 🔐 Default Credentials

### Odoo

| Field | Value |
|-------|-------|
| URL | http://localhost:8069 |
| Username | admin |
| Password | admin |

### Django Admin

| Field | Value |
|-------|-------|
| URL | http://localhost:8000/admin/ |
| Username | (Create with `python manage.py createsuperuser`) |
| Password | (Set during creation) |

---

## 📚 Documentation Files

Created for your reference:

1. **[SETUP_ARCH_LINUX.md](SETUP_ARCH_LINUX.md)** - Django + React setup guide
   - Virtual environment details
   - PostgreSQL configuration
   - Migration and static file management
   - Troubleshooting

2. **[SETUP_ODOO.md](SETUP_ODOO.md)** - Odoo 19 setup guide
   - Odoo 19 installation
   - Custom module management
   - Database operations
   - Integration with Django

3. **README.md** - System architecture overview
   - Project structure
   - Technology stack
   - Integration points

---

## ⚡ Automation Scripts

Four shell scripts have been created to simplify operations:

### `setup-arch-linux.sh`
Automates Django/frontend setup:
- Verifies virtual environment
- Checks PostgreSQL connectivity
- Creates databases
- Runs migrations
- Collects static files

### `setup-odoo.sh`
Automates Odoo setup:
- Verifies Odoo installation
- Validates configuration
- Creates Odoo database
- Tests PostgreSQL connection

### `start_odoo.sh`
Standalone Odoo server startup:
- Activates Python environment
- Starts Odoo on port 8069
- Manages process lifecycle
- Logs to `/tmp/odoo19.log`

### `start_all.sh`
Unified startup for both systems:
- Starts Odoo on port 8069
- Starts Django on port 8000
- Manages both processes
- Handles graceful shutdown

---

## 🔧 Environment Files

### `.env` (Django Configuration)
Created with development defaults:
```env
DEBUG=True
SECRET_KEY=dev-secret-key-***
ALLOWED_HOSTS=localhost,127.0.0.1,*.local
DB_NAME=alba_capital
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

### `odoo-local.conf` (Odoo Configuration)
Updated with correct paths:
```ini
addons_path = /home/nick/Alba/odoo_addons,/home/nick/Alba/odoo19/addons
admin_passwd = admin
db_host = localhost
db_user = nick
db_name = alba_staging
http_port = 8069
```

---

## 📦 Installed Python Packages

### Django Environment (33 packages)
- Django 5.2.12
- djangorestframework 3.15.2
- django-allauth 65.15.1
- psycopg2-binary 2.9.9
- gunicorn 23.0.0
- Plus 28 others

### Odoo Environment (60+ packages)
- Odoo 19.0
- PostgreSQL adapter
- Image processing (Pillow)
- PDF generation (reportlab)
- XML processing (lxml)
- Excel handling (openpyxl)
- Plus 50+ additional dependencies

---

## 🚀 Next Steps

1. **Install PostgreSQL:**
   ```bash
   sudo pacman -S postgresql postgresql-libs
   sudo systemctl start postgresql
   ```

2. **Run Setup Scripts:**
   ```bash
   cd /home/nick/Alba
   ./setup-arch-linux.sh
   ./setup-odoo.sh
   ```

3. **Start Servers:**
   ```bash
   # Terminal 1
   ./start_odoo.sh
   
   # Terminal 2
   source venv/bin/activate
   python manage.py runserver
   
   # Terminal 3
   cd frontend && npm run dev
   ```

4. **Access Systems:**
   - Odoo: http://localhost:8069 (admin/admin)
   - Django API: http://localhost:8000
   - Frontend: http://localhost:5173

---

## 🔗 System Integration

The three systems work together:

```
┌─────────────────────┐
│  React Frontend     │ Port 5173
│  (Customer Portal)  │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Django Backend     │ Port 8000
│  (REST API)         │
└──────────┬──────────┘
           │
           ↔️ API Bridge
           │
           ↓
┌─────────────────────┐
│  Odoo 19 Back-office│ Port 8069
│  (Loan Management)  │
└─────────────────────┘
           │
           ↓
      PostgreSQL
      localhost:5432
```

---

## 📖 Documentation Reference

- **Django:** See [SETUP_ARCH_LINUX.md](SETUP_ARCH_LINUX.md)
- **Odoo:** See [SETUP_ODOO.md](SETUP_ODOO.md)
- **Architecture:** See [README.md](README.md)
- **Deployment:** See [DEPLOYMENT_PRODUCTION.md](DEPLOYMENT_PRODUCTION.md)

---

## ✨ Summary

**Python 3.12 environments fully configured for:**
- ✅ Django 5.2.12 backend
- ✅ React 18.2 frontend with Vite
- ✅ Odoo 19 Community Edition
- ✅ PostgreSQL integration ready
- ✅ Custom Alba addons ready for deployment

**Status:** Ready for development 🚀

**Next action:** Install PostgreSQL and run `./setup-arch-linux.sh`

---

Generated: 2026-06-08  
System: Arch Linux  
User: nick  
