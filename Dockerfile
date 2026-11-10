FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Collect static files at build time. The throwaway key is only used by this command.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only-key python manage.py collectstatic --noinput

EXPOSE 8000
# Migrations are run on start so a fresh database is ready; use a release step instead if you run many replicas.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --access-logfile -"]
