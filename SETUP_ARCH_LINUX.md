# Alba Capital — Arch Linux Setup Guide

**Python 3.12 Environment Setup**  
Generated: 2026-06-08

---

## ✅ What's Been Done

Your Alba Capital environment has been initialized on Arch Linux with:

- ✓ **Python 3.12.13** virtual environment created at `./venv`
- ✓ **Django 5.2.12** and all Python dependencies installed
- ✓ **React 18.2.0** frontend with Vite and all npm dependencies installed
- ✓ **`.env` file** created with development defaults for PostgreSQL

---

## 📋 Pre-requisites

Before running the system, you need PostgreSQL installed and running:

### 1. Install PostgreSQL

```bash
sudo pacman -S postgresql postgresql-libs
```

### 2. Initialize the Database Cluster

```bash
sudo -u postgres initdb -D /var/lib/postgres/data
```

### 3. Start PostgreSQL Service

```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql  # Enable on boot
```

### 4. Verify PostgreSQL is Running

```bash
psql -U postgres -h localhost -c "SELECT version();"
```

### 5. Set PostgreSQL Password (Optional but Recommended)

```bash
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

---

## 🚀 Quick Start

### Option A: Automated Setup (Recommended)

Run the automated setup script which will:
- Verify the virtual environment
- Check PostgreSQL connectivity
- Create the database
- Run migrations
- Collect static files

```bash
cd /home/nick/Alba
./setup-arch-linux.sh
```

### Option B: Manual Setup

#### 1. Activate Virtual Environment

```bash
cd /home/nick/Alba
source venv/bin/activate
```

You should see `(venv)` in your prompt.

#### 2. Verify Python & Django

```bash
python --version       # Should be 3.12.13
django-admin --version # Should be 5.2.12
```

#### 3. Create PostgreSQL Database

```bash
createdb -U postgres alba_capital
```

#### 4. Apply Django Migrations

```bash
python manage.py migrate
```

#### 5. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

#### 6. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

---

## 🎯 Running the Application

### Backend (Django) — Port 8000

```bash
source venv/bin/activate
cd /home/nick/Alba
python manage.py runserver
```

Access: **http://localhost:8000**  
Admin: **http://localhost:8000/admin/**

### Frontend (React/Vite) — Port 5173

In a new terminal:

```bash
cd /home/nick/Alba/frontend
npm run dev
```

Access: **http://localhost:5173**

### Build Frontend for Production

```bash
cd /home/nick/Alba/frontend
npm run build
```

---

## 📝 Environment Configuration

The `.env` file in the project root contains all configuration:

```env
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=alba_capital
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

For production, change `DEBUG=False` and set strong values.

---

## 🔍 Troubleshooting

### PostgreSQL Connection Error

```
Error: connection to server at "localhost" (127.0.0.1), port 5432 failed
```

**Solution:**
```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Start it if not running
sudo systemctl start postgresql
```

### Python Package Installation Issues

If `pip install -r requirements.txt` fails:

```bash
# Upgrade pip, setuptools, and wheel
pip install --upgrade pip setuptools wheel

# Try installing again
pip install -r requirements.txt
```

### Cannot Find `psycopg2`

If you get import errors for psycopg2-binary:

```bash
# Already installed, verify:
pip list | grep psycopg2

# If missing, reinstall:
pip install psycopg2-binary==2.9.9
```

### Database Migration Errors

```bash
# Show migration status
python manage.py showmigrations

# Roll back a migration (if needed)
python manage.py migrate core 0001  # Goes back to 0001_initial
```

---

## 📂 Project Structure

```
Alba/
├── venv/                    # Python 3.12 virtual environment
├── config/                  # Django project configuration
├── core/                    # Core Django app (KYC, auth, verification)
├── loans/                   # Loans Django app
├── frontend/                # React/Vite frontend (npm dependencies)
├── odoo_addons/            # Odoo 19 integration modules
├── templates/              # Django HTML templates
├── static/                 # Static files (CSS, JS, images)
├── manage.py              # Django management command
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (created)
└── setup-arch-linux.sh    # Setup automation script (created)
```

---

## 🔧 Development Workflow

### Running Tests

```bash
source venv/bin/activate
python manage.py test
```

### Database Shell

```bash
python manage.py dbshell  # PostgreSQL prompt
```

### Django Shell (Python REPL)

```bash
python manage.py shell
```

### Making Migrations

```bash
# After modifying models.py:
python manage.py makemigrations
python manage.py migrate
```

---

## 🌐 Integration with Odoo

This project integrates with **Odoo 19 Enterprise** via custom addons in `odoo_addons/`.

To connect Odoo:
1. Set up Odoo 19 separately with your Odoo Enterprise license
2. Configure webhook URLs in `.env`
3. Test API connectivity using `curl` or Postman

---

## 📚 Useful Commands

| Command | Purpose |
|---------|---------|
| `source venv/bin/activate` | Activate virtual environment |
| `deactivate` | Exit virtual environment |
| `pip freeze` | List installed packages |
| `python manage.py createsuperuser` | Create admin user |
| `python manage.py check` | Verify project configuration |
| `python manage.py runserver 0.0.0.0:8000` | Listen on all interfaces |
| `npm run dev` | Start Vite dev server |
| `npm run build` | Build frontend for production |

---

## ⚡ Performance Tips

1. **Use SQLite for local testing** if PostgreSQL feels slow
2. **Enable caching** in settings for production
3. **Use Gunicorn + Nginx** for production deployment
4. **Minify frontend assets** before deploying

---

## 📞 Support

For issues:
1. Check the **Troubleshooting** section above
2. Review Django logs: `less /tmp/django.log`
3. Check PostgreSQL logs: `sudo journalctl -u postgresql -n 20`
4. Check `.env` configuration matches your system

---

**Happy coding! 🚀**
