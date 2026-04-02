# Production Deployment Guide

Deploy the Document Verification feature on your production Django server.

## Prerequisites

- Ubuntu 20.04+ server (or similar Linux)
- Python 3.10+
- Node.js 18+
- Nginx (recommended) or Apache
- SSL certificate (Let's Encrypt)

## Production Setup Steps

### 1. Install Node.js 18+ on Server

```bash
# Using NodeSource (recommended)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify
node --version  # v18.x.x
npm --version   # 9.x.x
```

### 2. Build Production Assets

On your development machine or CI/CD:

```bash
# Navigate to frontend
cd /path/to/your/project/frontend

# Install dependencies
npm ci --production

# Build for production
npm run build

# This creates static files in:
# loan_system/static/verification/
```

### 3. Deploy to Production Server

**Option A: Manual Deployment**

```bash
# On production server
cd /opt/odoo/Alba  # Your Django project directory

# Pull latest code
git pull origin main

# Build frontend (if building on server)
cd frontend
npm ci --production
npm run build
cd ..

# Collect Django static files
python manage.py collectstatic --noinput

# Restart services
sudo systemctl restart gunicorn
sudo systemctl restart nginx
```

**Option B: Automated Deployment (GitHub Actions)**

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Build Frontend
        run: |
          cd frontend
          npm ci
          npm run build
      
      - name: Deploy to Server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.HOST }}
          username: ${{ secrets.USERNAME }}
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/odoo/Alba
            git pull origin main
            python manage.py collectstatic --noinput
            python manage.py migrate
            sudo systemctl restart gunicorn
```

### 4. Nginx Configuration

Create `/etc/nginx/sites-available/alba`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # SSL Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Django Media Files
    location /media/ {
        alias /opt/odoo/Alba/media/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
    
    # Django Static Files (includes React build)
    location /static/ {
        alias /opt/odoo/Alba/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Gzip compression for static assets
        gzip on;
        gzip_types text/css application/javascript image/svg+xml;
    }
    
    # Main Django Application
    location / {
        proxy_pass http://unix:/run/gunicorn.sock;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # Timeouts for large file uploads
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
        client_max_body_size 50M;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/alba /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5. Gunicorn Systemd Service

Create `/etc/systemd/system/gunicorn.service`:

```ini
[Unit]
Description=Django Gunicorn Daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/odoo/Alba
Environment="PATH=/opt/odoo/Alba/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=loan_system.settings_production"
Environment="SECRET_KEY=your-production-secret-key"
Environment="DEBUG=False"
Environment="ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com"

ExecStart=/opt/odoo/Alba/venv/bin/gunicorn \
    --access-logfile - \
    --workers 4 \
    --bind unix:/run/gunicorn.sock \
    loan_system.wsgi:application

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
```

### 6. Production Settings (`settings_production.py`)

```python
from .settings import *

DEBUG = False

ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# Database - use production database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'alba_production',
        'USER': 'alba_user',
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Static Files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

# Media Files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Security
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# CORS (for API)
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
]

# File Upload Settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB
FILE_UPLOAD_PERMISSIONS = 0o644
```

### 7. SSL Certificate (Let's Encrypt)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal test
sudo certbot renew --dry-run
```

### 8. File Permissions

```bash
# Set ownership
sudo chown -R www-data:www-data /opt/odoo/Alba

# Set permissions
sudo chmod -R 755 /opt/odoo/Alba/static
sudo chmod -R 755 /opt/odoo/Alba/media
sudo chmod 644 /opt/odoo/Alba/db.sqlite3  # If using SQLite

# Ensure gunicorn can write to /run
sudo mkdir -p /run
touch /run/gunicorn.sock
sudo chown www-data:www-data /run/gunicorn.sock
```

### 9. Environment Variables

Create `/opt/odoo/Alba/.env.production`:

```bash
DJANGO_SETTINGS_MODULE=loan_system.settings_production
SECRET_KEY=your-super-secret-production-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_PASSWORD=your-secure-db-password
ODOO_API_KEY=your-odoo-api-key
ODOO_WEBHOOK_SECRET=your-webhook-secret
```

### 10. Health Check Endpoint

Add to your Django `urls.py`:

```python
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({'status': 'healthy', 'service': 'alba'})

urlpatterns = [
    # ... existing URLs
    path('health/', health_check, name='health_check'),
]
```

## Deployment Checklist

- [ ] Node.js 18+ installed on server
- [ ] Frontend built (`npm run build`)
- [ ] Static files collected (`collectstatic`)
- [ ] Nginx configured with SSL
- [ ] Gunicorn service enabled
- [ ] Database migrated
- [ ] Environment variables set
- [ ] File permissions correct
- [ ] Firewall configured (allow 80, 443)
- [ ] Health check endpoint working
- [ ] Log rotation configured

## Troubleshooting Production Issues

### 1. Static Files Not Loading

```bash
# Check static files location
ls -la /opt/odoo/Alba/static/verification/

# Rebuild and recollect
cd /opt/odoo/Alba/frontend && npm run build
cd /opt/odoo/Alba && python manage.py collectstatic --noinput
sudo systemctl restart nginx
```

### 2. Permission Denied on Media Uploads

```bash
sudo chown -R www-data:www-data /opt/odoo/Alba/media
sudo chmod -R 755 /opt/odoo/Alba/media
```

### 3. CORS Errors in Production

Add to `settings_production.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
]
CORS_ALLOW_CREDENTIALS = True
```

### 4. 413 Request Entity Too Large (File Uploads)

In Nginx config:
```nginx
client_max_body_size 50M;
```

In Gunicorn service:
```ini
Environment="DATA_UPLOAD_MAX_MEMORY_SIZE=52428800"
```

## Monitoring & Logging

### Gunicorn Logs
```bash
sudo journalctl -u gunicorn -f
```

### Nginx Logs
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Django Logs
Configure in `settings_production.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/django/alba.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
```

## Backup Strategy

### Database Backup
```bash
# Add to crontab (daily at 2 AM)
0 2 * * * /usr/bin/pg_dump alba_production | gzip > /backups/alba_$(date +\%Y\%m\%d).sql.gz
```

### Media Files Backup
```bash
# Add to crontab (daily at 3 AM)
0 3 * * * rsync -avz /opt/odoo/Alba/media/ /backups/media/
```

---

**After deployment, your verification feature will be available at:**
```
https://yourdomain.com/client/profile/
```

All on a single system - no separate ports, no CORS issues, fully integrated with Django.
