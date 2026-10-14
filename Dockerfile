FROM python:3.13.16-alpine3.23@sha256:07b20c774a247152e74f622034c1482495d299e070eec620ddff13e01264290b AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt ./requirements.txt
RUN /opt/venv/bin/python -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt \
    && /opt/venv/bin/python -m pip check

FROM python:3.13.16-alpine3.23@sha256:07b20c774a247152e74f622034c1482495d299e070eec620ddff13e01264290b AS runtime
ARG APP_UID=10001
ARG APP_GID=10001
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data
WORKDIR /app
RUN test "$APP_UID" -gt 0 && test "$APP_GID" -gt 0 \
    && addgroup -g "$APP_GID" app \
    && adduser -D -H -u "$APP_UID" -G app app \
    && mkdir /data && chown "$APP_UID:$APP_GID" /data
COPY --from=builder /opt/venv /opt/venv
COPY api.py ./api.py
COPY order_manager/ ./order_manager/
COPY static/ ./static/
COPY docker/entrypoint.sh ./docker/entrypoint.sh
RUN chmod 0555 /app/docker/entrypoint.sh
USER ${APP_UID}:${APP_GID}
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=20s --retries=3 \
    CMD ["python", "-m", "order_manager.healthcheck"]
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
