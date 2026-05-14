#!/bin/bash
# ADN Solutions – Quick Setup Script
echo "=== ADN uPVC & Aluminum Solutions – Setup ==="

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser (optional)
echo ""
echo "Create admin superuser? (y/n)"
read -r RESP
if [ "$RESP" = "y" ]; then
  python manage.py createsuperuser
fi

echo ""
echo "=== Setup complete! ==="
echo "Run: python manage.py runserver"
echo "Open: http://127.0.0.1:8000/"
