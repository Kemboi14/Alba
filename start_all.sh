#!/bin/bash

# Alba Capital — Start Both Django & Odoo 19
# Usage: ./start_all.sh

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
DJANGO_VENV="$ALBA_DIR/venv"
ODOO_VENV="$ALBA_DIR/odoo_venv"
ODOO_PATH="$ALBA_DIR/odoo19"
ODOO_CONFIG="$ALBA_DIR/odoo-local.conf"
DJANGO_LOG="/tmp/django.log"
ODOO_LOG="/tmp/odoo19.log"
DJANGO_PID_FILE="/tmp/django.pid"
ODOO_PID_FILE="/tmp/odoo19.pid"
DB_NAME="alba_staging"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ── Cleanup on exit ──────────────────────────────────────────
stop_all() {
    echo ""
    echo -e "${YELLOW}Stopping servers...${NC}"
    
    if [ -f "$ODOO_PID_FILE" ]; then
        kill "$(cat "$ODOO_PID_FILE")" 2>/dev/null
        rm -f "$ODOO_PID_FILE"
    fi
    
    if [ -f "$DJANGO_PID_FILE" ]; then
        kill "$(cat "$DJANGO_PID_FILE")" 2>/dev/null
        rm -f "$DJANGO_PID_FILE"
    fi
    
    pkill -f "odoo-bin" 2>/dev/null || true
    pkill -f "manage.py runserver" 2>/dev/null || true
    
    echo -e "${GREEN}All servers stopped.${NC}"
    exit 0
}

trap stop_all SIGINT SIGTERM

echo "=========================================================="
echo "  Alba Capital — Django + Odoo 19 (Python 3.12)"
echo "=========================================================="
echo ""

# Kill any stale instances
pkill -f "odoo-bin" 2>/dev/null || true
pkill -f "manage.py runserver" 2>/dev/null || true
sleep 1

# ── START ODOO ────────────────────────────────────────────────
echo -e "${YELLOW}[1/2] Starting Odoo 19 on http://localhost:8069 ...${NC}"
source "$ODOO_VENV/bin/activate"

cd "$ALBA_DIR"
nohup "$ODOO_PATH/odoo-bin" \
    --config="$ODOO_CONFIG" \
    -d "$DB_NAME" \
    --logfile="$ODOO_LOG" \
    > /dev/null 2>&1 &

ODOO_PID=$!
echo "$ODOO_PID" > "$ODOO_PID_FILE"

sleep 2

if ps -p "$ODOO_PID" > /dev/null; then
    echo -e "${GREEN}✓ Odoo started (PID: $ODOO_PID)${NC}"
else
    echo -e "${RED}✗ Odoo failed to start${NC}"
    echo "  Logs: $ODOO_LOG"
fi

deactivate

echo ""

# ── START DJANGO ──────────────────────────────────────────────
echo -e "${YELLOW}[2/2] Starting Django on http://localhost:8000 ...${NC}"
source "$DJANGO_VENV/bin/activate"

cd "$ALBA_DIR"
nohup python manage.py runserver 0.0.0.0:8000 \
    > "$DJANGO_LOG" 2>&1 &

DJANGO_PID=$!
echo "$DJANGO_PID" > "$DJANGO_PID_FILE"

sleep 2

if ps -p "$DJANGO_PID" > /dev/null; then
    echo -e "${GREEN}✓ Django started (PID: $DJANGO_PID)${NC}"
else
    echo -e "${RED}✗ Django failed to start${NC}"
    echo "  Logs: $DJANGO_LOG"
fi

echo ""
echo "=========================================================="
echo -e "${GREEN}✓ Both servers started!${NC}"
echo "=========================================================="
echo ""
echo "Services:"
echo "  • Odoo 19:      http://localhost:8069 (admin/admin)"
echo "  • Django:       http://localhost:8000"
echo "  • Django Admin: http://localhost:8000/admin/"
echo ""
echo "Logs:"
echo "  • Odoo:   tail -f $ODOO_LOG"
echo "  • Django: tail -f $DJANGO_LOG"
echo ""
echo "Press Ctrl+C to stop all servers"
echo ""

# Keep script running until interrupted
wait
