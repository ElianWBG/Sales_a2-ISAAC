web: python manage.py collectstatic --noinput && python manage.py migrate && python manage.py setup_roles && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 60
