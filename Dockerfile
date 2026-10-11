FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main --no-cache

COPY . .
# SECRET_KEY factice : uniquement pour collecter les fichiers statiques au build.
RUN SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app \
    && mkdir /data && chown app:app /data
USER app

# Base SQLite persistée dans le volume /data (surchargeable par DATABASE_URL).
ENV DATABASE_URL=sqlite:////data/db.sqlite3
VOLUME /data
EXPOSE 8000

# Le Host envoyé doit faire partie d'ALLOWED_HOSTS.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request as u; h = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')[0]; u.urlopen(u.Request('http://127.0.0.1:8000/health/', headers={'Host': h}), timeout=4)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
