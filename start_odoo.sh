#!/bin/bash

# Alba Capital — Start Odoo 19 Server
# Usage: ./start_odoo.sh

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
ODOO_VENV="$ALBA_DIR/odoo_venv"
ODOO_PATH="$ALBA_DIR/odoo19"
ODOO_CONFIG="$ALBA_DIR/odoo-local.conf"
ODOO_LOG="/tmp/odoo19.log"
ODOO_PID_FILE="/tmp/odoo19.pid"
DB_NAME="alba_staging"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ── Cleanup on exit ──────────────────────────────────────────
stop_odoo() {
    echo ""
    echo -e "${YELLOW}Stopping Odoo...${NC}"
    [ -f "$ODOO_PID_FILE" ] && kill "$(cat "$ODOO_PID_FILE")" 2>/dev/null && rm -f "$ODOO_PID_FILE"
    pkill -f "odoo-bin" 2>/dev/null || true
    echo -e "${GREEN}Odoo stopped.${NC}"
    exit 0
}

trap stop_odoo SIGINT SIGTERM

echo "=========================================================="
echo "  Alba Capital — Odoo 19 Server"
echo "=========================================================="
echo ""

# Kill any stale Odoo instances
pkill -f "odoo-bin" 2>/dev/null || true
sleep 1

# Activate virtual environment
echo -e "${YELLOW}[1/2] Activating Python 3.12 environment...${NC}"
source "$ODOO_VENV/bin/activate"
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Failed to activate virtual environment${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Environment activated (Python $(python --version 2>&1 | awk '{print $2}'))${NC}"
echo ""

# Start Odoo
echo -e "${YELLOW}[2/2] Starting Odoo 19 on http://localhost:8069 ...${NC}"
cd "$ALBA_DIR"

nohup "$ODOO_PATH/odoo-bin" \
    --config="$ODOO_CONFIG" \
    -d "$DB_NAME" \
    --logfile="$ODOO_LOG" \
    > /dev/null 2>&1 &

ODOO_PID=$!
echo "$ODOO_PID" > "$ODOO_PID_FILE"

# Give Odoo a moment to start
sleep 2

if ps -p "$ODOO_PID" > /dev/null; then
    echo -e "${GREEN}✓ Odoo started successfully (PID: $ODOO_PID)${NC}"
    echo ""
    echo "Server Details:"
    echo "  URL: http://localhost:8069"
    echo "  Database: $DB_NAME"
    echo "  Config: $ODOO_CONFIG"
    echo "  Logs: $ODOO_LOG"
    echo ""
    echo "View live logs with: tail -f $ODOO_LOG"
    echo "Press Ctrl+C to stop Odoo"
    echo ""
    
    # Keep script running
    wait $ODOO_PID
else
    echo -e "${RED}✗ Failed to start Odoo${NC}"
    echo ""
    echo "Check logs at: $ODOO_LOG"
    exit 1
fi
