# The API, the worker and the scheduler: one image, three commands.
# Build from the repository root:  docker build -f api/Dockerfile -t wfm-api .
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src
# The engine is a path dependency of the API, so both go in.
COPY engine/ engine/
COPY api/pyproject.toml api/uv.lock api/
RUN cd api && uv sync --frozen --no-dev --no-install-project
COPY api/ api/
RUN cd api && uv sync --frozen --no-dev
# Static files for WhiteNoise. The build needs a key to import the settings, not the real one.
RUN cd api && DJANGO_SECRET_KEY=build-only DJANGO_SETTINGS_MODULE=config.settings.prod \
    .venv/bin/python manage.py collectstatic --noinput

FROM python:3.12-slim
# OR-Tools and Prophet need the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 wfm
COPY --from=build --chown=wfm:wfm /src /src
WORKDIR /src/api
ENV PATH="/src/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod
USER wfm
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
# The API. The worker and scheduler override this command (see deploy/docker-compose.yml).
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
