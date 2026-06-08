#!/bin/bash

# Alba Capital — Master Startup Script
# Activates environments and starts all systems
# Usage: ./run.sh [all|odoo|django|frontend]

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
DJANGO_VENV="$ALBA_DIR/venv"
ODOO_VENV="$ALBA_DIR/odoo_venv"
ODOO_PATH="$ALBA_DIR/odoo19"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default action
ACTION="${1:-all}"

# ── Display menu ──────────────────────────────────────────────
show_menu() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}     Alba Capital — System Startup${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Available options:"
    echo "  ./run.sh all       → Start all servers (Odoo + Django + Frontend)"
    echo "  ./run.sh odoo      → Start only Odoo 19"
    echo "  ./run.sh django    → Start only Django"
    echo "  ./run.sh frontend  → Start only React Frontend"
    echo "  ./run.sh help      → Show this menu"
    echo ""
}

# ── Start Odoo ─────────────────────────────────────────────────
start_odoo() {
    echo -e "${YELLOW}[Starting Odoo 19]${NC}"
    source "$ODOO_VENV/bin/activate"
    cd "$ALBA_DIR"
    
    # Start in background
    nohup "$ODOO_PATH/odoo-bin" \
        --config="$ALBA_DIR/odoo-local.conf" \
        -d alba_staging \
        --logfile="/tmp/odoo19.log" \
        > /dev/null 2>&1 &
    
    ODOO_PID=$!
    echo "$ODOO_PID" > /tmp/odoo19.pid
    sleep 2
    
    if ps -p "$ODOO_PID" > /dev/null; then
        echo -e "${GREEN}✓ Odoo started (PID: $ODOO_PID)${NC}"
        echo -e "  URL: http://localhost:8069 (admin/admin)"
        return 0
    else
        echo -e "${RED}✗ Odoo failed to start${NC}"
        return 1
    fi
}

# ── Start Django ───────────────────────────────────────────────
start_django() {
    echo -e "${YELLOW}[Starting Django Backend]${NC}"
    
    # Check if running in a new terminal
    if [ "$TERM" = "dumb" ] || [ -z "$TERM" ]; then
        echo -e "${YELLOW}Note: Running Django in background mode${NC}"
        source "$DJANGO_VENV/bin/activate"
        cd "$ALBA_DIR"
        nohup python manage.py runserver 0.0.0.0:8000 \
            > /tmp/django.log 2>&1 &
        
        DJANGO_PID=$!
        echo "$DJANGO_PID" > /tmp/django.pid
        sleep 2
        
        if ps -p "$DJANGO_PID" > /dev/null; then
            echo -e "${GREEN}✓ Django started (PID: $DJANGO_PID)${NC}"
            echo -e "  URL: http://localhost:8000"
            echo -e "  Logs: tail -f /tmp/django.log"
            return 0
        fi
    else
        echo -e "${GREEN}✓ Django ready to start${NC}"
        echo -e "${YELLOW}In your terminal, run:${NC}"
        echo ""
        echo "  source $DJANGO_VENV/bin/activate"
        echo "  cd $ALBA_DIR"
        echo "  python manage.py runserver"
        echo ""
        return 0
    fi
}

# ── Start Frontend ─────────────────────────────────────────────
start_frontend() {
    echo -e "${YELLOW}[Starting React Frontend]${NC}"
    echo -e "${GREEN}✓ Frontend ready to start${NC}"
    echo -e "${YELLOW}In a new terminal, run:${NC}"
    echo ""
    echo "  cd $ALBA_DIR/frontend"
    echo "  npm run dev"
    echo ""
    return 0
}

# ── Show status ────────────────────────────────────────────────
show_status() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}     System Status${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo ""
    
    # Check Odoo
    if ps aux | grep -q "[o]doo-bin"; then
        ODOO_PID=$(pgrep -f "odoo-bin" | head -1)
        echo -e "${GREEN}✓ Odoo 19${NC} (PID: $ODOO_PID)"
        echo "  URL: http://localhost:8069"
    else
        echo -e "${RED}✗ Odoo 19${NC} (not running)"
    fi
    
    # Check Django
    if ps aux | grep -q "[m]anage.py runserver"; then
        DJANGO_PID=$(pgrep -f "manage.py runserver" | head -1)
        echo -e "${GREEN}✓ Django${NC} (PID: $DJANGO_PID)"
        echo "  URL: http://localhost:8000"
    else
        echo -e "${RED}✗ Django${NC} (not running)"
    fi
    
    # Check Frontend
    if ps aux | grep -q "[v]ite"; then
        VITE_PID=$(pgrep -f "vite" | head -1)
        echo -e "${GREEN}✓ React Frontend${NC} (PID: $VITE_PID)"
        echo "  URL: http://localhost:5173"
    else
        echo -e "${RED}✗ React Frontend${NC} (not running)"
    fi
    
    echo ""
}

# ── Stop all servers ───────────────────────────────────────────
stop_all() {
    echo -e "${YELLOW}Stopping all servers...${NC}"
    pkill -f "odoo-bin" 2>/dev/null && echo -e "${GREEN}✓ Odoo stopped${NC}"
    pkill -f "manage.py runserver" 2>/dev/null && echo -e "${GREEN}✓ Django stopped${NC}"
    pkill -f "vite" 2>/dev/null && echo -e "${GREEN}✓ Frontend stopped${NC}"
    echo ""
}

# ── Main logic ─────────────────────────────────────────────────

case "$ACTION" in
    all)
        echo -e "${GREEN}Starting all systems...${NC}"
        start_odoo
        sleep 1
        start_django
        start_frontend
        show_status
        echo -e "${YELLOW}To stop all servers, run:${NC} ./run.sh stop"
        ;;
    odoo)
        start_odoo
        show_status
        ;;
    django)
        start_django
        ;;
    frontend)
        start_frontend
        ;;
    status)
        show_status
        ;;
    stop)
        stop_all
        ;;
    logs)
        echo -e "${YELLOW}Odoo logs:${NC}"
        tail -f /tmp/odoo19.log
        ;;
    help|--help|-h)
        show_menu
        ;;
    *)
        echo -e "${RED}Unknown option: $ACTION${NC}"
        show_menu
        exit 1
        ;;
esac
