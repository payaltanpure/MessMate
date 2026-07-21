# Deployment Checklist

## Environment
- [ ] Copy `.env.example` values into a real `.env` file on the deployment server.
- [ ] Set `SECRET_KEY` to a strong production secret.
- [ ] Set `DEBUG=False`.
- [ ] Set `ALLOWED_HOSTS` to your real domain names.
- [ ] Configure `GEMINI_API_KEY` and payment keys if required.

## Database
- [ ] Run database migrations.
- [ ] Create or restore a production database.
- [ ] Ensure the database is writable and backed up.

## Static and Media Files
- [ ] Collect static files with `python manage.py collectstatic`.
- [ ] Configure a persistent media storage location for uploads.
- [ ] Ensure the web server serves `/static/` and `/media/` correctly.

## Security
- [ ] Enable HTTPS.
- [ ] Restrict admin access and use strong authentication.
- [ ] Review allowed hosts, CORS, and secret handling.

## Process
- [ ] Install production dependencies from `requirements-prod.txt`.
- [ ] Start the app with Gunicorn or your preferred production server.
- [ ] Confirm health checks and application startup.
