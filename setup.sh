#!/bin/bash

# Alba Capital ERP Setup Script
# This script automates the initial setup process

echo "================================"
echo "Alba Capital ERP Setup"
echo "================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

echo "✓ Python 3 is installed"

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "Warning: PostgreSQL is not installed or not in PATH."
    echo "Please install PostgreSQL 14+ and create a database."
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created. Please edit it with your configuration."
else
    echo "✓ .env file already exists"
fi

# Create logs directory
echo ""
echo "Creating logs directory..."
mkdir -p logs
echo "✓ Logs directory created"

# Create media directories
echo ""
echo "Creating media directories..."
mkdir -p media/kyc/ids media/kyc/residence media/kyc/payslips media/kyc/statements
mkdir -p media/profile_pictures media/investor_statements
echo "✓ Media directories created"

# Run migrations
echo ""
echo "Would you like to run database migrations now? (y/n)"
read -r run_migrations

if [ "$run_migrations" = "y" ]; then
    echo ""
    echo "Running migrations..."
    python manage.py makemigrations
    python manage.py migrate
    echo "✓ Migrations completed"
    
    # Create superuser
    echo ""
    echo "Would you like to create a superuser? (y/n)"
    read -r create_superuser
    
    if [ "$create_superuser" = "y" ]; then
        python manage.py createsuperuser
    fi
fi

# Collect static files
echo ""
echo "Would you like to collect static files? (y/n)"
read -r collect_static

if [ "$collect_static" = "y" ]; then
    python manage.py collectstatic --noinput
    echo "✓ Static files collected"
fi

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Create PostgreSQL database if not done already"
echo "3. Run: python manage.py migrate"
echo "4. Run: python manage.py createsuperuser"
echo "5. Run: python manage.py runserver"
echo ""
echo "Access the system at: http://localhost:8000"
echo ""
