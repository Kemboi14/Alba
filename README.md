# Alba Capital ERP System

A production-grade Enterprise Resource Planning (ERP) system built with Django 5, PostgreSQL, and Tailwind CSS.

## 📋 Overview

This comprehensive ERP system manages all core business operations for Alba Capital, including:

- **Loan Management**: Complete loan lifecycle from application to repayment
- **Accounting**: Double-entry bookkeeping with automated journal entries
- **Investor Management**: Portfolio tracking with compound interest calculation
- **Payroll & HR**: Employee management with statutory deductions
- **CRM**: Lead tracking and customer relationship management
- **Asset Management**: Fixed asset register with automated depreciation
- **Reporting**: Comprehensive financial and operational reports

## 🏗️ Technology Stack

- **Backend**: Django 5.0.2
- **Database**: PostgreSQL
- **Frontend**: Django Templates + Tailwind CSS
- **Task Queue**: Celery + Redis
- **Financial Calculations**: Python Decimal (precision-safe)

## 📁 Project Structure

```
loan_system/
├── apps/
│   ├── core/              # Authentication, users, roles, audit logs
│   ├── accounting/        # Double-entry bookkeeping, GL, reports
│   ├── loans/             # Loan management, applications, repayments
│   ├── investors/         # Investment accounts, compound interest
│   ├── payroll/           # Payroll processing, leave management
│   ├── crm/               # Lead tracking, customer interactions
│   ├── assets/            # Fixed asset management, depreciation
│   └── reporting/         # Report generation and scheduling
├── config/                # Django settings and configuration
├── static/                # Static files (CSS, JS, images)
├── templates/             # HTML templates
├── media/                 # User-uploaded files
└── manage.py
```

## 🚀 Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis (for Celery)
- Node.js (for Tailwind CSS)

### Setup Steps

1. **Clone the repository**
   ```bash
   cd loan_system
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Create PostgreSQL database**
   ```bash
   sudo -u postgres psql
   CREATE DATABASE alba_erp;
   CREATE USER alba_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE alba_erp TO alba_user;
   \q
   ```

6. **Run migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

7. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

8. **Install Tailwind CSS** (Optional, if customizing)
   ```bash
   npm install -g tailwindcss
   ```

9. **Collect static files**
   ```bash
   python manage.py collectstatic
   ```

10. **Run development server**
    ```bash
    python manage.py runserver
    ```

Access the system at: `http://localhost:8000`

## ⚙️ Configuration

### Essential Environment Variables

```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=alba_erp
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-password

# SMS Gateway (Africa's Talking)
SMS_API_KEY=your-api-key
SMS_USERNAME=your-username

# M-Pesa Integration
MPESA_CONSUMER_KEY=your-key
MPESA_CONSUMER_SECRET=your-secret
MPESA_SHORTCODE=your-paybill
```

## 🔧 Running Background Tasks

Start Celery worker for background tasks:
```bash
celery -A config worker -l info
```

Start Celery beat for scheduled tasks:
```bash
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## 📊 Key Features

### 1. Loan Management
- Multiple loan products (Salary Advance, Business Loans, Asset Financing)
- Automated credit scoring
- Repayment schedule generation
- Payment tracking and reconciliation
- NPL classification and monitoring

### 2. Accounting System
- Double-entry bookkeeping
- Automated journal entries
- Chart of accounts management
- Financial reports (P&L, Balance Sheet, Trial Balance)
- Bank reconciliation

### 3. Investor Management
- Compound interest calculation
- Withdrawal penalty enforcement (no interest if withdrawn in month)
- Automated monthly statements
- Portfolio dashboards

### 4. Payroll Processing
- Salary calculation
- Statutory deductions (PAYE, NSSF, NHIF)
- Leave management
- Bank payment integration

### 5. Security & Audit
- Role-based access control (RBAC)
- Comprehensive audit trail
- Session management
- Multi-factor authentication support

## 🧪 Running Tests

```bash
python manage.py test
```

## 📱 Production Deployment

### Using Gunicorn

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Using Docker (Optional)

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /static/ {
        alias /path/to/staticfiles/;
    }

    location /media/ {
        alias /path/to/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📚 Module Documentation

### Core Module
- User management with custom User model
- Role-based permissions
- Audit logging for all actions
- System settings management

### Accounting Module
- Chart of Accounts (COA)
- Journal entries with validation
- Fiscal year management
- Budgeting and variance analysis

### Loans Module
- Loan products configuration
- Customer KYC management
- Application workflow
- Disbursement and repayment tracking

### Investors Module
- Investment accounts
- Compound interest with withdrawal penalties
- Monthly statement generation
- Portfolio analytics

## 🔒 Security Best Practices

1. Always use environment variables for sensitive data
2. Enable SSL/TLS in production
3. Keep SECRET_KEY secure and unique
4. Use strong passwords for database and admin accounts
5. Regular security updates: `pip install --upgrade -r requirements.txt`
6. Enable CSRF protection (default in Django)
7. Use HTTPS for all production deployments

## 🤝 Contributing

This is a proprietary system for Alba Capital. Contact the development team for contribution guidelines.

## 📄 License

Copyright © 2026 Softlink Options Ltd. All rights reserved.

## 📞 Support

For technical support:
- Email: support@softlinkoptions.com
- Phone: +254 XXX XXX XXX

## 🎯 Development Roadmap

- [ ] Mobile app integration
- [ ] Advanced analytics dashboard
- [ ] AI-powered credit scoring
- [ ] Blockchain integration for audit trail
- [ ] API webhooks for third-party integrations

---

**Built with ❤️ by Softlink Options Ltd for Alba Capital**
