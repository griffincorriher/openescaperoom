FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir /config \
    && chown app:app /config

COPY --chown=app:app app ./app
COPY --chown=app:app static ./static
COPY --chown=app:app rooms ./rooms
COPY --chown=app:app config.example.yaml .

ENV GAME_CONFIG_PATH=/config/config.yaml
USER app

EXPOSE 8000

CMD ["python", "-m", "app"]
