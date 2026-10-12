# Étape 1 : dépendances installées par Poetry dans un virtualenv (/app/.venv).
FROM python:3.13-slim AS deps

ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app
RUN pip install --no-cache-dir poetry==2.4.3
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-cache

# Étape 2 : image finale, sans Poetry, avec le seul virtualenv.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=deps /app/.venv /app/.venv
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

# Version affichée sur la page Utilisateurs (fournie par le workflow de publication).
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

# Le Host envoyé doit faire partie d'ALLOWED_HOSTS.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request as u; h = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')[0]; u.urlopen(u.Request('http://127.0.0.1:8000/health/', headers={'Host': h}), timeout=4)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
