#!/bin/bash

# Alba Capital — Quick Setup Guide
# System: Python 3.12 Virtual Environment on Arch Linux
# Created: 2026-06-08

echo "========================================================"
echo "   Alba Capital Setup — Python 3.12 Environment"
echo "========================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="$ALBA_DIR/venv"

# ── STEP 1: Verify Virtual Environment ──────────────────────
echo -e "${YELLOW}[Step 1] Checking Python Virtual Environment...${NC}"
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}✗ Virtual environment not found at $VENV_PATH${NC}"
    echo "  Run: python3.12 -m venv $VENV_PATH"
    exit 1
fi

if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo -e "${RED}✗ Virtual environment activation script not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Virtual environment found${NC}"
echo ""

# ── STEP 2: Activate Virtual Environment ────────────────────
echo -e "${YELLOW}[Step 2] Activating Virtual Environment...${NC}"
source "$VENV_PATH/bin/activate"
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo "  Python: $(python --version)"
echo "  Pip: $(pip --version | awk '{print $2}')"
echo ""

# ── STEP 3: Verify Database Connection ──────────────────────
echo -e "${YELLOW}[Step 3] Checking PostgreSQL Connection...${NC}"

if ! command -v psql &> /dev/null; then
    echo -e "${RED}✗ PostgreSQL client (psql) not found${NC}"
    echo "  Install: sudo pacman -S postgresql-libs"
    exit 1
fi

# Try to connect to the database
psql -U postgres -h localhost -d postgres -c "SELECT 1;" &> /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PostgreSQL is running and accessible${NC}"
else
    echo -e "${RED}✗ Cannot connect to PostgreSQL${NC}"
    echo ""
    echo "  SETUP REQUIRED:"
    echo "  1. Install PostgreSQL: sudo pacman -S postgresql"
    echo "  2. Initialize database: sudo -u postgres initdb -D /var/lib/postgres/data"
    echo "  3. Start service: sudo systemctl start postgresql"
    echo "  4. Enable on boot: sudo systemctl enable postgresql"
    echo ""
    echo "  Default password for 'postgres' user can be set with:"
    echo "  sudo -u postgres psql -c \"ALTER USER postgres PASSWORD 'postgres';\""
    echo ""
    exit 1
fi
echo ""

# ── STEP 4: Create Database (if not exists) ─────────────────
echo -e "${YELLOW}[Step 4] Setting up Database...${NC}"

DB_NAME="alba_capital"
DB_USER="postgres"
DB_HOST="localhost"

# Check if database exists
if psql -U "$DB_USER" -h "$DB_HOST" -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo -e "${GREEN}✓ Database '$DB_NAME' already exists${NC}"
else
    echo "  Creating database '$DB_NAME'..."
    createdb -U "$DB_USER" -h "$DB_HOST" "$DB_NAME"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Database created successfully${NC}"
    else
        echo -e "${RED}✗ Failed to create database${NC}"
        exit 1
    fi
fi
echo ""

# ── STEP 5: Run Django Migrations ──────────────────────────
echo -e "${YELLOW}[Step 5] Running Django Migrations...${NC}"
cd "$ALBA_DIR"
python manage.py migrate
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Migrations applied successfully${NC}"
else
    echo -e "${RED}✗ Migration failed${NC}"
    exit 1
fi
echo ""

# ── STEP 6: Create Superuser (Optional) ──────────────────────
echo -e "${YELLOW}[Step 6] Creating Superuser (Optional)${NC}"
echo "Run: python manage.py createsuperuser"
echo ""

# ── STEP 7: Collect Static Files ──────────────────────────────
echo -e "${YELLOW}[Step 7] Collecting Static Files...${NC}"
python manage.py collectstatic --noinput --clear
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Static files collected${NC}"
else
    echo -e "${YELLOW}⚠ Static file collection skipped or had warnings${NC}"
fi
echo ""

# ── FINAL: Ready to Run ──────────────────────────────────────
echo -e "${GREEN}========================================================"
echo "   ✓ Setup Complete!${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo "To start the development servers:"
echo ""
echo "  1. Django Backend (Port 8000):"
echo "     source $VENV_PATH/bin/activate"
echo "     cd $ALBA_DIR"
echo "     python manage.py runserver"
echo ""
echo "  2. Frontend Development Server (Port 5173):"
echo "     cd $ALBA_DIR/frontend"
echo "     npm run dev"
echo ""
echo "  3. Access the applications:"
echo "     - Django Admin: http://localhost:8000/admin/"
echo "     - Frontend: http://localhost:5173/"
echo ""
echo "Database Details:"
echo "     - Name: alba_capital"
echo "     - User: postgres"
echo "     - Host: localhost:5432"
echo ""
