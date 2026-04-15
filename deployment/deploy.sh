#!/usr/bin/env bash
# =====================================================================
#  Alba Loans — Server Deployment Script
#  Run as root on the production server (37.60.248.144)
#  Domain: loans.softlinkoptions.me.ke
# =====================================================================
set -euo pipefail

PROJECT_DIR="/opt/odoo/Alba"
VENV="$PROJECT_DIR/venv"
LOG_DIR="/var/log/alba-loans"
SERVICE_NAME="alba-loans"
DOMAIN="loans.softlinkoptions.me.ke"

echo "=== Step 1: Detect web server ==="
WEBSERVER=""
if systemctl is-active --quiet nginx 2>/dev/null; then
    WEBSERVER="nginx"
elif systemctl is-active --quiet apache2 2>/dev/null; then
    WEBSERVER="apache2"
fi
echo "Active web server: ${WEBSERVER:-none detected}"

echo ""
echo "=== Step 2: Install/update project dependencies ==="
cd "$PROJECT_DIR"
source "$VENV/bin/activate"
pip install -q -r requirements.txt
deactivate

echo ""
echo "=== Step 3: Build React frontend (requires Node.js) ==="
if command -v node &>/dev/null && command -v npm &>/dev/null; then
    cd "$PROJECT_DIR/frontend"
    npm ci --silent
    npm run build
    echo "React frontend built → $PROJECT_DIR/static/verification/"
else
    echo "SKIP: Node.js not found. Install with: curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs"
fi

echo ""
echo "=== Step 4: Django collectstatic + migrate ==="
cd "$PROJECT_DIR"
source "$VENV/bin/activate"
python manage.py migrate --no-input
python manage.py collectstatic --no-input -v 0
deactivate

echo ""
echo "=== Step 5: Create log directory ==="
mkdir -p "$LOG_DIR"
chown www-data:www-data "$LOG_DIR" || true

echo ""
echo "=== Step 6: Install Gunicorn systemd service ==="
cp "$PROJECT_DIR/deployment/alba-loans.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 2
systemctl status "$SERVICE_NAME" --no-pager -l

echo ""
echo "=== Step 7: Web server configuration ==="

if [[ "$WEBSERVER" == "nginx" ]]; then
    echo "Configuring nginx..."
    cp "$PROJECT_DIR/deployment/nginx-loans.conf" /etc/nginx/sites-available/"$DOMAIN"
    ln -sf /etc/nginx/sites-available/"$DOMAIN" /etc/nginx/sites-enabled/"$DOMAIN"
    nginx -t && systemctl reload nginx
    echo "nginx configured. Next: run certbot for SSL."
    echo "  certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@softlinkoptions.com"

elif [[ "$WEBSERVER" == "apache2" ]]; then
    echo "Configuring Apache (cPanel-safe ProxyPass)..."
    a2enmod proxy proxy_http headers 2>/dev/null || true
    # cPanel userdata include paths (survives apache rebuilds)
    UDATA_HTTP="/etc/apache2/conf.d/userdata/std/2_4/loans/${DOMAIN}"
    UDATA_SSL="/etc/apache2/conf.d/userdata/ssl/2_4/loans/${DOMAIN}"
    mkdir -p "$UDATA_HTTP" "$UDATA_SSL"

    cat > "$UDATA_HTTP/proxy.conf" <<'APACHECONF'
ProxyPreserveHost On
ProxyPass /static/ !
ProxyPass /media/ !
ProxyPass / unix:/run/alba-loans.sock|http://localhost/
ProxyPassReverse / /
RequestHeader set X-Forwarded-Proto "http"
APACHECONF

    cat > "$UDATA_SSL/proxy.conf" <<'APACHECONF'
ProxyPreserveHost On
ProxyPass /static/ !
ProxyPass /media/ !
ProxyPass / unix:/run/alba-loans.sock|http://localhost/
ProxyPassReverse / /
RequestHeader set X-Forwarded-Proto "https"
APACHECONF

    # cPanel alias for static + media
    cat >> "$UDATA_SSL/proxy.conf" <<APACHESTR

Alias /static/ ${PROJECT_DIR}/staticfiles/
Alias /media/  ${PROJECT_DIR}/media/
<Directory ${PROJECT_DIR}/staticfiles>
    Require all granted
</Directory>
<Directory ${PROJECT_DIR}/media>
    Require all granted
</Directory>
APACHESTR

    # Rebuild Apache config (cPanel way)
    if command -v /usr/local/cpanel/bin/apache_conf_distiller &>/dev/null; then
        /usr/local/cpanel/bin/apache_conf_distiller --update
    fi
    apachectl configtest && systemctl reload apache2
    echo "Apache configured. Enable AutoSSL in cPanel WHM for SSL."

else
    echo "No active nginx or apache2 found."
    echo "Installing nginx..."
    apt-get install -y nginx
    cp "$PROJECT_DIR/deployment/nginx-loans.conf" /etc/nginx/sites-available/"$DOMAIN"
    ln -sf /etc/nginx/sites-available/"$DOMAIN" /etc/nginx/sites-enabled/"$DOMAIN"
    systemctl enable nginx
    # Temporarily remove SSL block until cert is issued
    sed -i '/listen 443/,/^}/d' /etc/nginx/sites-available/"$DOMAIN"
    sed -i 's/return 301 https.*//' /etc/nginx/sites-available/"$DOMAIN"
    nginx -t && systemctl start nginx
    echo "nginx installed and started (HTTP only). Run certbot next:"
    echo "  apt install certbot python3-certbot-nginx -y"
    echo "  certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@softlinkoptions.com"
fi

echo ""
echo "================================================================"
echo "  Deployment complete!"
echo "  Gunicorn socket: /run/alba-loans.sock"
echo "  Logs:  journalctl -u $SERVICE_NAME -f"
echo "         tail -f $LOG_DIR/error.log"
echo "  Domain: https://$DOMAIN"
echo "================================================================"
