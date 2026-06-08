#!/bin/bash

# Alba Capital — Activate Environment
# Simple script to activate and prepare the environment for development
# Usage: source activate.sh

ALBA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Alba Capital — Environment Setup${NC}"
echo ""

# Check which environment to activate
if [ -z "$1" ] || [ "$1" = "django" ]; then
    echo -e "${GREEN}Activating Django environment (Python 3.12)...${NC}"
    source "$ALBA_DIR/venv/bin/activate"
    cd "$ALBA_DIR"
    echo -e "${GREEN}✓ Django environment activated${NC}"
    echo ""
    echo "To start Django server:"
    echo "  python manage.py runserver"
    echo ""
    
elif [ "$1" = "odoo" ]; then
    echo -e "${GREEN}Activating Odoo environment (Python 3.12)...${NC}"
    source "$ALBA_DIR/odoo_venv/bin/activate"
    cd "$ALBA_DIR"
    echo -e "${GREEN}✓ Odoo environment activated${NC}"
    echo ""
    echo "To start Odoo server:"
    echo "  ./odoo19/odoo-bin --config=./odoo-local.conf -d alba_staging"
    echo ""
    echo "Or use the startup script:"
    echo "  ./start_odoo.sh"
    echo ""
    
else
    echo -e "${YELLOW}Usage:${NC}"
    echo "  source activate.sh        # Activate Django environment"
    echo "  source activate.sh odoo   # Activate Odoo environment"
    echo ""
fi

echo -e "${GREEN}Current Python: $(python --version 2>&1)${NC}"
echo -e "${GREEN}Location: $ALBA_DIR${NC}"
