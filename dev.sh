#!/bin/bash

# Alba Capital — Multi-Window Startup (tmux)
# Starts all systems in separate tmux windows
# Usage: ./dev.sh [start|stop|status]

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
DJANGO_VENV="$ALBA_DIR/venv"
ODOO_VENV="$ALBA_DIR/odoo_venv"
ODOO_PATH="$ALBA_DIR/odoo19"
SESSION_NAME="alba-dev"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo -e "${RED}tmux is not installed. Install it with: sudo pacman -S tmux${NC}"
    echo ""
    echo "Alternative: Use ./run.sh instead"
    exit 1
fi

# ── Start all systems ──────────────────────────────────────────
start_systems() {
    echo -e "${BLUE}═════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Alba Capital — Starting Development Environment${NC}"
    echo -e "${BLUE}═════════════════════════════════════════════════════${NC}"
    echo ""
    
    # Kill existing session if it exists
    tmux kill-session -t $SESSION_NAME 2>/dev/null
    sleep 1
    
    # Create new session
    tmux new-session -d -s $SESSION_NAME -x 200 -y 50
    
    # Window 1: Odoo 19
    echo -e "${YELLOW}[1/3] Starting Odoo 19...${NC}"
    tmux new-window -t $SESSION_NAME -n odoo
    tmux send-keys -t $SESSION_NAME:odoo "cd $ALBA_DIR && source $ODOO_VENV/bin/activate && $ODOO_PATH/odoo-bin --config=$ALBA_DIR/odoo-local.conf -d alba_staging" Enter
    sleep 3
    
    # Window 2: Django
    echo -e "${YELLOW}[2/3] Starting Django...${NC}"
    tmux new-window -t $SESSION_NAME -n django
    tmux send-keys -t $SESSION_NAME:django "cd $ALBA_DIR && source $DJANGO_VENV/bin/activate && python manage.py runserver 0.0.0.0:8000" Enter
    sleep 2
    
    # Window 3: Frontend
    echo -e "${YELLOW}[3/3] Starting React Frontend...${NC}"
    tmux new-window -t $SESSION_NAME -n frontend
    tmux send-keys -t $SESSION_NAME:frontend "cd $ALBA_DIR/frontend && npm run dev" Enter
    sleep 2
    
    # Window 4: Control panel (optional)
    tmux new-window -t $SESSION_NAME -n logs
    tmux send-keys -t $SESSION_NAME:logs "echo 'Alba Capital Development Session'; echo ''; echo 'Servers running:'; ps aux | grep -E '(odoo-bin|manage.py|vite)' | grep -v grep; echo ''; echo 'To switch windows: Ctrl+B then type :select-window -t odoo (or django, frontend, logs)'; echo ''; bash" Enter
    
    echo ""
    echo -e "${GREEN}✓ All systems started!${NC}"
    echo ""
    echo "System Status:"
    echo -e "  ${GREEN}✓ Odoo 19${NC}     → http://localhost:8069 (admin/admin)"
    echo -e "  ${GREEN}✓ Django${NC}      → http://localhost:8000"
    echo -e "  ${GREEN}✓ Frontend${NC}    → http://localhost:5173"
    echo ""
    echo "tmux Windows:"
    echo "  • odoo     - Odoo 19 server"
    echo "  • django   - Django backend"
    echo "  • frontend - React frontend"
    echo "  • logs     - Control & monitoring"
    echo ""
    echo "Commands:"
    echo "  tmux attach -t $SESSION_NAME           - Attach to session"
    echo "  tmux list-windows -t $SESSION_NAME     - List windows"
    echo "  tmux kill-session -t $SESSION_NAME     - Stop all servers"
    echo ""
    echo "Keyboard shortcuts (inside tmux):"
    echo "  Ctrl+B + c         - Create new window"
    echo "  Ctrl+B + n/p       - Next/Previous window"
    echo "  Ctrl+B + [0-4]     - Switch to window number"
    echo "  Ctrl+B + d         - Detach session"
    echo "  Ctrl+B + x         - Kill window (or Ctrl+C in server window)"
    echo ""
}

# ── Stop all systems ───────────────────────────────────────────
stop_systems() {
    echo -e "${YELLOW}Stopping all systems...${NC}"
    
    if tmux has-session -t $SESSION_NAME 2>/dev/null; then
        tmux kill-session -t $SESSION_NAME
        echo -e "${GREEN}✓ All systems stopped${NC}"
    else
        echo -e "${YELLOW}Session not found${NC}"
    fi
    echo ""
}

# ── Show status ────────────────────────────────────────────────
show_status() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Development Environment Status${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
    echo ""
    
    if tmux has-session -t $SESSION_NAME 2>/dev/null; then
        echo -e "${GREEN}tmux session '$SESSION_NAME' is${NC} ${GREEN}running${NC}"
        echo ""
        echo "Windows:"
        tmux list-windows -t $SESSION_NAME
        echo ""
        
        # Check individual services
        if ps aux | grep -q "[o]doo-bin"; then
            echo -e "  ${GREEN}✓ Odoo 19${NC} (http://localhost:8069)"
        else
            echo -e "  ${RED}✗ Odoo 19${NC} (not responding)"
        fi
        
        if ps aux | grep -q "[m]anage.py runserver"; then
            echo -e "  ${GREEN}✓ Django${NC} (http://localhost:8000)"
        else
            echo -e "  ${RED}✗ Django${NC} (not responding)"
        fi
        
        if ps aux | grep -q "[v]ite"; then
            echo -e "  ${GREEN}✓ React Frontend${NC} (http://localhost:5173)"
        else
            echo -e "  ${RED}✗ Frontend${NC} (not responding)"
        fi
    else
        echo -e "${RED}No session running${NC}"
        echo ""
        echo "Start with: ./dev.sh start"
    fi
    echo ""
}

# ── Main logic ─────────────────────────────────────────────────

ACTION="${1:-start}"

case "$ACTION" in
    start)
        start_systems
        echo -e "${YELLOW}Attaching to session in 2 seconds...${NC}"
        sleep 2
        tmux attach-session -t $SESSION_NAME
        ;;
    stop)
        stop_systems
        ;;
    status)
        show_status
        ;;
    attach)
        if tmux has-session -t $SESSION_NAME 2>/dev/null; then
            tmux attach-session -t $SESSION_NAME
        else
            echo -e "${RED}Session not running. Start with: ./dev.sh start${NC}"
            exit 1
        fi
        ;;
    *)
        echo -e "${BLUE}Alba Capital — Development Environment Manager${NC}"
        echo ""
        echo "Usage: ./dev.sh [command]"
        echo ""
        echo "Commands:"
        echo "  start   - Start all systems in tmux (default)"
        echo "  stop    - Stop all systems"
        echo "  status  - Show system status"
        echo "  attach  - Attach to existing session"
        echo ""
        echo "Examples:"
        echo "  ./dev.sh start          # Start everything"
        echo "  ./dev.sh status         # Check what's running"
        echo "  ./dev.sh stop           # Stop all systems"
        echo ""
        exit 0
        ;;
esac
