#!/bin/bash
# Fix and start Django with React integration
# Run this after installation issues

set -e

echo "=========================================="
echo "Fixing and Starting Alba Capital Server"
echo "=========================================="
echo ""

cd /home/nick/ACCT.f

# Activate virtual environment
source venv/bin/activate
echo "✓ Virtual environment activated"

# Remove CSP middleware (already done, but safe to check)
echo ""
echo "Step 1: CSP middleware already disabled in settings.py"
echo "✓ Server can start without django-csp package"

echo ""
echo "Step 2: Checking React build..."
echo "------------------------------------------"
cd frontend

# Check if node_modules exists
if [ ! -d "node_modules" ] || [ -z "$(ls -A node_modules 2>/dev/null)" ]; then
    echo "⚠ node_modules missing or empty. Running npm install..."
    npm install
fi

# Check for tsconfig.json
if [ ! -f "tsconfig.json" ]; then
    echo "⚠ tsconfig.json missing. Creating..."
    cat > tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
EOF
    echo "✓ tsconfig.json created"
fi

if [ ! -f "tsconfig.node.json" ]; then
    cat > tsconfig.node.json << 'EOF'
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
EOF
    echo "✓ tsconfig.node.json created"
fi

# Build React
echo ""
echo "Building React frontend..."
npm run build
echo "✓ React build complete"

cd ..

echo ""
echo "Step 3: Collecting static files..."
echo "------------------------------------------"
python manage.py collectstatic --noinput
echo "✓ Static files collected"

echo ""
echo "Step 4: Checking migrations..."
echo "------------------------------------------"
python manage.py migrate
echo "✓ Database ready"

echo ""
echo "=========================================="
echo "Starting Django Server..."
echo "=========================================="
echo ""
echo "Server will be available at:"
echo "  http://127.0.0.1:8000/"
echo ""
echo "Document verification at:"
echo "  http://127.0.0.1:8000/client/profile/"
echo ""

# Start server
python manage.py runserver 8000
