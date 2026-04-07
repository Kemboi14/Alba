#!/usr/bin/env bash
# Alba Capital — Development Server
# Usage: ./start_server.sh

set -e

cd "$(dirname "$0")"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "venv312" ]; then
    source venv312/bin/activate
else
    echo "ERROR: No virtual environment found. Create one with:"
    echo "  python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "Alba Capital — Development Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Apply any pending migrations
echo "Checking migrations..."
python manage.py migrate --run-syncdb 2>/dev/null || python manage.py migrate

# Collect static files silently
python manage.py collectstatic --no-input --clear -v 0

echo "Starting Django on http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."
echo ""
python manage.py runserver 8000
