#!/usr/bin/env bash
# Alba Capital — Start Both Servers (Odoo + Django)
# Usage: ./start_server.sh

ALBA_DIR="$(cd "$(dirname "$0")" && pwd)"
DJANGO_PYTHON="$ALBA_DIR/venv312/bin/python"
ODOO_VENV="/home/juliuskorir/odoo_venv"
ODOO_BIN="/home/juliuskorir/odoo19_community/odoo-bin"
ODOO_CONF="/home/juliuskorir/odoo.conf"
ODOO_ADDONS="/home/juliuskorir/odoo19_community/addons,$ALBA_DIR/odoo_addons"
ODOO_LOG="/tmp/odoo19.log"
DJANGO_LOG="/tmp/django.log"
ODOO_PID_FILE="/tmp/odoo19.pid"
DJANGO_PID_FILE="/tmp/django.pid"

stop_servers() {
    echo ""
    echo "Stopping servers..."
    [ -f "$ODOO_PID_FILE" ]   && kill "$(cat "$ODOO_PID_FILE")"   2>/dev/null && rm -f "$ODOO_PID_FILE"
    [ -f "$DJANGO_PID_FILE" ] && kill "$(cat "$DJANGO_PID_FILE")" 2>/dev/null && rm -f "$DJANGO_PID_FILE"
    pkill -f "odoo-bin"           2>/dev/null || true
    pkill -f "manage.py runserver" 2>/dev/null || true
    echo "Servers stopped."
    exit 0
}

trap stop_servers SIGINT SIGTERM

echo "================================================"
echo "  Alba Capital — Odoo 19 + Django"
echo "================================================"

# ── Kill any stale instances ──────────────────────
pkill -f "odoo-bin"            2>/dev/null || true
pkill -f "manage.py runserver" 2>/dev/null || true
sleep 1

# ── Start Odoo ────────────────────────────────────
echo "[1/3] Starting Odoo 19 on http://localhost:8069 ..."
source "$ODOO_VENV/bin/activate"
nohup "$ODOO_BIN" \
    --config="$ODOO_CONF" \
    --addons-path="$ODOO_ADDONS" \
    > "$ODOO_LOG" 2>&1 &
ODOO_PID=$!
echo "$ODOO_PID" > "$ODOO_PID_FILE"
deactivate

# ── Apply Django migrations & collect static ─────
echo "[2/3] Applying Django migrations..."
cd "$ALBA_DIR"
"$DJANGO_PYTHON" manage.py migrate --no-input 2>&1 | grep -E "Apply|No migrations|Error" || true
"$DJANGO_PYTHON" manage.py collectstatic --no-input -v 0 2>/dev/null || true

# ── Start Django ──────────────────────────────────
echo "[3/3] Starting Django on http://127.0.0.1:8000 ..."
nohup "$DJANGO_PYTHON" manage.py runserver 8000 \
    > "$DJANGO_LOG" 2>&1 &
DJANGO_PID=$!
echo "$DJANGO_PID" > "$DJANGO_PID_FILE"

# ── Wait for ports to open ────────────────────────
echo ""
echo "Waiting for servers to come up..."
for i in $(seq 1 15); do
    sleep 1
    ODOO_UP=false; DJANGO_UP=false
    ss -tlnp | grep -q ':8069' && ODOO_UP=true
    ss -tlnp | grep -q ':8000' && DJANGO_UP=true
    if $ODOO_UP && $DJANGO_UP; then break; fi
done

echo ""
echo "================================================"
$ODOO_UP   && echo "  ✔ Odoo 19   → http://localhost:8069"   || echo "  ✗ Odoo failed to start — check $ODOO_LOG"
$DJANGO_UP && echo "  ✔ Django    → http://127.0.0.1:8000"   || echo "  ✗ Django failed to start — check $DJANGO_LOG"
echo ""
echo "  Logs:"
echo "    Odoo:   tail -f $ODOO_LOG"
echo "    Django: tail -f $DJANGO_LOG"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo "================================================"

# ── Keep script alive (so Ctrl+C works) ──────────
wait
