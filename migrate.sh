#!/bin/bash
# Django Migration Script for Document Verification Feature
# Run this script to apply all database migrations

set -e  # Exit on error

echo "=========================================="
echo "Django Migration - Document Verification"
echo "=========================================="
echo ""

# Change to project directory
cd /home/nick/ACCT.f

# Activate virtual environment
echo "Step 1: Activating virtual environment..."
echo "------------------------------------------"
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated (venv)"
elif [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "✓ Virtual environment activated (.venv)"
elif [ -d "env" ]; then
    source env/bin/activate
    echo "✓ Virtual environment activated (env)"
else
    echo "⚠ No virtual environment found, using system Python"
fi
echo ""

echo "Step 2: Checking for unapplied migrations..."
echo "------------------------------------------"
python manage.py showmigrations --plan 2>/dev/null | grep -E "\[ \]" || echo "All migrations already applied or checking..."
echo ""

echo "Step 3: Creating new migrations..."
echo "------------------------------------------"
python manage.py makemigrations loan_system
echo ""

echo "Step 4: Applying migrations..."
echo "------------------------------------------"
python manage.py migrate
echo ""

echo "Step 5: Verifying migrations..."
echo "------------------------------------------"
python manage.py showmigrations | grep -E "loan_system" | tail -5
echo ""

echo "Step 6: Collecting static files..."
echo "------------------------------------------"
python manage.py collectstatic --noinput
echo ""

echo "=========================================="
echo "Migration Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Restart your Django server: python manage.py runserver"
echo "2. Test the document verification feature at /client/profile/"
echo ""
echo "To start the server:"
echo "  source venv/bin/activate && python manage.py runserver 8000"
