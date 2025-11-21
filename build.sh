#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install Python dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Collect static files (uncomment this line if you want to collect static files during build)
# python manage.py collectstatic --no-input
