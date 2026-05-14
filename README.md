# ADN uPVC & Aluminum Solutions – Business Management System

A professional Django web application for managing Quotations and Invoices for ADN uPVC & Aluminum Solutions, Arusha Tanzania.

## Features

### Quotations
- Auto-generated quote numbers (QT-YYYY-XXXX)
- Multi-item specification (windows & doors with dimensions)
- Multiple material options with live price comparison
- Discount support (percentage or fixed amount)
- Tanzanian tax support: VAT, Service Levy, Skills Levy, Withholding Tax + 2 custom taxes
- Status tracking: Draft → Sent → Accepted / Rejected / Expired
- Professional PDF/print output (per material option)
- One-click convert quotation to invoice

### Invoices
- Auto-generated invoice numbers (ADN-YYYY-XXXX)
- Linked to quotations
- Payment tracking with multiple installments
- Payment methods: Bank Transfer, Mobile Money, Cash, Cheque
- Status: Draft → Sent → Paid / Overdue / Cancelled
- Professional PDF/print with PAID/OVERDUE stamp
- Auto-mark overdue invoices

### Dashboard
- Live stats: total quotes, accepted, pending, invoices, revenue
- Recent activity overview

## Quick Start

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open: http://127.0.0.1:8000/
Admin: http://127.0.0.1:8000/admin/

## Tech Stack
- **Backend**: Django 4.2, SQLite
- **Frontend**: Bootstrap 5, Bootstrap Icons, Inter font
- **PDF**: Browser print-to-PDF
