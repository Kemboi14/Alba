#!/bin/bash
# Complete Installation Script for Alba Capital with Document Verification
# This script installs all dependencies and sets up the environment

set -e  # Exit on error

echo "=========================================="
echo "Alba Capital - Complete Installation"
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
    echo "⚠ No virtual environment found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✓ Virtual environment created and activated"
fi
echo ""

# Install/Upgrade pip
echo "Step 2: Upgrading pip..."
echo "------------------------------------------"
pip install --upgrade pip
echo "✓ Pip upgraded"
echo ""

# Install Python dependencies
echo "Step 3: Installing Python/Django dependencies..."
echo "------------------------------------------"

# Check if requirements.txt exists
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✓ Requirements from requirements.txt installed"
else
    echo "⚠ requirements.txt not found. Installing core dependencies..."
    
    # Install core Django and required packages
    pip install django>=4.2.0
    pip install djangorestframework
    pip install django-cors-headers
    pip install django-csp
    pip install psycopg2-binary
    pip install Pillow
    pip install python-dotenv
    pip install requests
    pip install celery
    pip install redis
    pip install gunicorn
    pip install whitenoise
    
    echo "✓ Core dependencies installed"
fi
echo ""

# Create static directory
echo "Step 4: Creating static directory..."
echo "------------------------------------------"
mkdir -p static
mkdir -p media
mkdir -p staticfiles
echo "✓ Static directories created"
echo ""

# Install Node.js dependencies
echo "Step 5: Installing React/Node.js dependencies..."
echo "------------------------------------------"
if [ -d "frontend" ]; then
    cd frontend
    
    # Check if package.json exists
    if [ -f "package.json" ]; then
        # Check if node_modules exists
        if [ ! -d "node_modules" ]; then
            echo "Installing npm packages..."
            npm install
            echo "✓ Node.js dependencies installed"
        else
            echo "✓ Node_modules already exists"
        fi
    else
        echo "⚠ package.json not found in frontend directory"
    fi
    
    cd ..
else
    echo "⚠ Frontend directory not found"
fi
echo ""

# Create .env file if it doesn't exist
echo "Step 6: Setting up environment variables..."
echo "------------------------------------------"
if [ ! -f ".env" ]; then
    cat > .env << EOF
DEBUG=True
SECRET_KEY=your-secret-key-here-change-in-production
ALLOWED_HOSTS=localhost,127.0.0.1,*.ngrok.io
DATABASE_URL=sqlite:///db.sqlite3
REDIS_URL=redis://localhost:6379/0
EOF
    echo "✓ .env file created (please update with your settings)"
else
    echo "✓ .env file already exists"
fi
echo ""

# Run Django migrations
echo "Step 7: Creating and applying Django migrations..."
echo "------------------------------------------"

# Make migrations for all apps
python manage.py makemigrations core loans
echo "✓ Migrations created"

# Apply migrations
python manage.py migrate
echo "✓ Migrations applied"
echo ""

# Collect static files
echo "Step 8: Collecting static files..."
echo "------------------------------------------"
python manage.py collectstatic --noinput
echo "✓ Static files collected"
echo ""

# Build React frontend
echo "Step 9: Building React frontend..."
echo "------------------------------------------"
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    cd frontend
    npm run build
    cd ..
    echo "✓ React frontend built"
else
    echo "⚠ Frontend build skipped (no frontend directory or package.json)"
fi
echo ""

# Create superuser if needed
echo "Step 10: Setup complete!"
echo "------------------------------------------"
echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Update .env file with your production settings"
echo "2. Create a superuser: python manage.py createsuperuser"
echo "3. Start the server: python manage.py runserver 8000"
echo ""
echo "To start the server now:"
echo "  source venv/bin/activate && python manage.py runserver 8000"
echo ""
echo "Document verification feature will be available at:"
echo "  http://localhost:8000/client/profile/"
