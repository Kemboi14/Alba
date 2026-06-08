#!/bin/bash

# Alba Capital — Odoo 19 Setup & Configuration
# Arch Linux with Python 3.12
# Created: 2026-06-08

echo "=========================================================="
echo "   Alba Capital — Odoo 19 Setup (Python 3.12)"
echo "=========================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
ODOO_VENV="$ALBA_DIR/odoo_venv"
ODOO_PATH="$ALBA_DIR/odoo19"
ODOO_CONFIG="$ALBA_DIR/odoo-local.conf"
DB_NAME="alba_staging"
DB_USER="nick"
DB_HOST="localhost"
DB_PORT="5432"

# ── STEP 1: Verify Virtual Environment ──────────────────────
echo -e "${YELLOW}[Step 1] Checking Odoo Virtual Environment...${NC}"
if [ ! -d "$ODOO_VENV" ]; then
    echo -e "${RED}✗ Odoo virtual environment not found at $ODOO_VENV${NC}"
    echo "  Run: python3.12 -m venv $ODOO_VENV"
    exit 1
fi

if [ ! -f "$ODOO_VENV/bin/activate" ]; then
    echo -e "${RED}✗ Odoo virtual environment activation script not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Odoo virtual environment found${NC}"
echo ""

# ── STEP 2: Verify Odoo Installation ────────────────────────
echo -e "${YELLOW}[Step 2] Verifying Odoo 19 Installation...${NC}"
if [ ! -d "$ODOO_PATH" ]; then
    echo -e "${RED}✗ Odoo 19 installation not found at $ODOO_PATH${NC}"
    echo "  Run: git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git odoo19"
    exit 1
fi

if [ ! -f "$ODOO_PATH/odoo-bin" ]; then
    echo -e "${RED}✗ Odoo binary not found at $ODOO_PATH/odoo-bin${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Odoo 19 installation found${NC}"
echo ""

# ── STEP 3: Activate Virtual Environment ────────────────────
echo -e "${YELLOW}[Step 3] Activating Odoo Virtual Environment...${NC}"
source "$ODOO_VENV/bin/activate"
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo "  Python: $(python --version)"
echo "  Pip: $(pip --version | awk '{print $2}')"
echo ""

# ── STEP 4: Verify Dependencies ──────────────────────────────
echo -e "${YELLOW}[Step 4] Verifying Odoo Dependencies...${NC}"
python -c "import odoo; print(f'✓ Odoo {odoo.release.version} installed')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Odoo dependencies not properly installed${NC}"
    echo "  Attempting to install missing dependencies..."
    cd "$ODOO_PATH"
    pip install -e . -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Failed to install Odoo dependencies${NC}"
        exit 1
    fi
fi
echo -e "${GREEN}✓ Odoo dependencies verified${NC}"
echo ""

# ── STEP 5: Check PostgreSQL Connection ──────────────────────
echo -e "${YELLOW}[Step 5] Checking PostgreSQL Connection...${NC}"

if ! command -v psql &> /dev/null; then
    echo -e "${RED}✗ PostgreSQL client (psql) not found${NC}"
    echo "  Install: sudo pacman -S postgresql-libs"
    exit 1
fi

# Try to connect to the database
psql -U "$DB_USER" -h "$DB_HOST" -d postgres -c "SELECT 1;" &> /dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PostgreSQL is running and accessible${NC}"
else
    echo -e "${RED}✗ Cannot connect to PostgreSQL${NC}"
    echo ""
    echo "  SETUP REQUIRED:"
    echo "  1. Install PostgreSQL: sudo pacman -S postgresql"
    echo "  2. Initialize database: sudo -u postgres initdb -D /var/lib/postgres/data"
    echo "  3. Start service: sudo systemctl start postgresql"
    echo "  4. Create user 'nick': sudo -u postgres createuser -d nick"
    echo ""
    exit 1
fi
echo ""

# ── STEP 6: Create Odoo Database (if not exists) ─────────────
echo -e "${YELLOW}[Step 6] Setting up Odoo Database...${NC}"

# Check if database exists
if psql -U "$DB_USER" -h "$DB_HOST" -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    echo -e "${GREEN}✓ Database '$DB_NAME' already exists${NC}"
else
    echo "  Creating database '$DB_NAME'..."
    createdb -U "$DB_USER" -h "$DB_HOST" "$DB_NAME" -O "$DB_USER"
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Database created successfully${NC}"
    else
        echo -e "${YELLOW}⚠ Database may already exist or creation failed${NC}"
    fi
fi
echo ""

# ── STEP 7: Verify Configuration File ────────────────────────
echo -e "${YELLOW}[Step 7] Verifying Odoo Configuration...${NC}"

if [ ! -f "$ODOO_CONFIG" ]; then
    echo -e "${RED}✗ Configuration file not found at $ODOO_CONFIG${NC}"
    exit 1
fi

# Check key settings
grep -q "addons_path" "$ODOO_CONFIG"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Configuration file is valid${NC}"
    echo "  Config location: $ODOO_CONFIG"
else
    echo -e "${RED}✗ Configuration file is incomplete${NC}"
    exit 1
fi
echo ""

# ── FINAL: Ready to Run ──────────────────────────────────────
echo -e "${GREEN}========================================================"
echo "   ✓ Odoo Setup Complete!${NC}"
echo -e "${GREEN}========================================================${NC}"
echo ""
echo "To start Odoo 19:"
echo ""
echo "  source $ODOO_VENV/bin/activate"
echo "  cd $ALBA_DIR"
echo "  $ODOO_PATH/odoo-bin --config=$ODOO_CONFIG -d $DB_NAME"
echo ""
echo "Or use the startup script:"
echo ""
echo "  ./start_odoo.sh"
echo ""
echo "Access Odoo at: http://localhost:8069"
echo "Admin Username: admin"
echo "Admin Password: admin"
echo ""
echo "Database Details:"
echo "  - Name: $DB_NAME"
echo "  - User: $DB_USER"
echo "  - Host: $DB_HOST:$DB_PORT"
echo ""
echo "Custom Addons Location:"
echo "  $ALBA_DIR/odoo_addons"
echo ""
